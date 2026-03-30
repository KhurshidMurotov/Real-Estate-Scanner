from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import asyncio
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from real_estate_scanner.config import settings
from real_estate_scanner.db.crud import (
    get_sale_broadcast_state,
    upsert_sale_broadcast_state,
    upsert_user,
)
from real_estate_scanner.db.init_db import init_db
from real_estate_scanner.db.models import SaleBroadcastState
from real_estate_scanner.db.session import AsyncSessionLocal
from real_estate_scanner.parser.worker import (
    APARTMENTS_BUTTON,
    COMMERCIAL_BUTTON,
    SCRAPING_LOOP_DELAY_SECONDS,
    SEND_INTERVAL_SECONDS,
    STOP_BUTTON,
    run_scraping_pass,
    run_worker,
    send_broadcast_step_for_user,
)

logger = logging.getLogger(__name__)
_LOCAL_TZ = ZoneInfo("Asia/Tashkent")
_scraping_task: asyncio.Task | None = None

router = Router()


def _setup_logging() -> None:
    project_root = Path(__file__).resolve().parents[3]
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "scanner.log"

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def _build_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=APARTMENTS_BUTTON)],
            [KeyboardButton(text=COMMERCIAL_BUTTON)],
            [KeyboardButton(text=STOP_BUTTON)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _state_payload(
    *,
    user_id: int,
    existing: SaleBroadcastState | None,
    is_active: bool | None = None,
    apartments_enabled: bool | None = None,
    commercial_enabled: bool | None = None,
    is_paused: bool | None = None,
    started_at=None,
    window_start=None,
    window_end=None,
    last_batch_at=None,
    total_found: int | None = None,
    pending_ads: list[dict] | None = None,
    sent_olx_ids: list[str] | None = None,
) -> dict:
    return {
        "user_id": user_id,
        "is_active": bool(existing.is_active) if is_active is None and existing else bool(is_active),
        "apartments_enabled": bool(existing.apartments_enabled) if apartments_enabled is None and existing else bool(apartments_enabled),
        "commercial_enabled": bool(existing.commercial_enabled) if commercial_enabled is None and existing else bool(commercial_enabled),
        "is_paused": bool(existing.is_paused) if is_paused is None and existing else bool(is_paused),
        "started_at": existing.started_at if started_at is None and existing else started_at,
        "window_start": existing.window_start if window_start is None and existing else window_start,
        "window_end": existing.window_end if window_end is None and existing else window_end,
        "last_batch_at": existing.last_batch_at if last_batch_at is None and existing else last_batch_at,
        "total_found": int(existing.total_found) if total_found is None and existing else int(total_found or 0),
        "pending_ads": list(existing.pending_ads or []) if pending_ads is None and existing else list(pending_ads or []),
        "sent_olx_ids": list(existing.sent_olx_ids or []) if sent_olx_ids is None and existing else list(sent_olx_ids or []),
    }


async def _ensure_broadcast_state(session, *, user_id: int, username: str | None) -> SaleBroadcastState:
    await upsert_user(session=session, user_id=user_id, username=username)
    state = await get_sale_broadcast_state(session, user_id)
    if state is not None:
        return state
    await upsert_sale_broadcast_state(
        session,
        **_state_payload(user_id=user_id, existing=None),
    )
    state = await get_sale_broadcast_state(session, user_id)
    assert state is not None
    return state


async def _run_scraping_loop() -> None:
    global _scraping_task
    try:
        logger.info("Global scraping loop started")
        while True:
            await run_scraping_pass()
            await asyncio.sleep(SCRAPING_LOOP_DELAY_SECONDS)
    except asyncio.CancelledError:
        logger.info("Global scraping loop cancelled")
        raise
    except Exception:
        logger.exception("Global scraping loop failed")
    finally:
        _scraping_task = None


def _scraping_running() -> bool:
    return _scraping_task is not None and not _scraping_task.done()


async def _activate_subscription(
    *,
    message: Message,
    enable_apartments: bool = False,
    enable_commercial: bool = False,
) -> None:
    user_id = message.from_user.id
    now = datetime.now(_LOCAL_TZ)

    async with AsyncSessionLocal() as session:
        state = await _ensure_broadcast_state(session, user_id=user_id, username=message.from_user.username)
        requested_already_enabled = (
            (enable_apartments and state.apartments_enabled)
            or (enable_commercial and state.commercial_enabled)
        )

        if state.is_paused:
            new_apartments_enabled = bool(enable_apartments)
            new_commercial_enabled = bool(enable_commercial)
            await upsert_sale_broadcast_state(
                session,
                **_state_payload(
                    user_id=user_id,
                    existing=state,
                    is_active=new_apartments_enabled or new_commercial_enabled,
                    apartments_enabled=new_apartments_enabled,
                    commercial_enabled=new_commercial_enabled,
                    is_paused=False,
                    started_at=state.started_at or now,
                    last_batch_at=None,
                    pending_ads=[],
                ),
            )

            if new_apartments_enabled and new_commercial_enabled:
                text = (
                    f"Подписки на квартиры и коммерцию включены. Отправка идёт из базы каждые "
                    f"{SEND_INTERVAL_SECONDS} секунд, от самого старого объявления к новому."
                )
            elif new_apartments_enabled:
                text = (
                    f"Подписка на квартиры включена. Отправка идёт из базы каждые "
                    f"{SEND_INTERVAL_SECONDS} секунд, от самого старого объявления к новому."
                )
            else:
                text = (
                    f"Подписка на коммерцию включена. Отправка идёт из базы каждые "
                    f"{SEND_INTERVAL_SECONDS} секунд, от самого старого объявления к новому."
                )

            await message.answer(text, reply_markup=_build_keyboard())
            await send_broadcast_step_for_user(bot=message.bot, user_id=user_id, force=True)
            return

        if requested_already_enabled and state.is_active and not state.is_paused:
            await upsert_sale_broadcast_state(
                session,
                **_state_payload(
                    user_id=user_id,
                    existing=state,
                    is_active=True,
                    is_paused=True,
                    pending_ads=[],
                ),
            )
            await message.answer(
                "Повторное нажатие поставило рассылку на паузу. Нажмите «Стоп» ещё раз, чтобы продолжить.",
                reply_markup=_build_keyboard(),
            )
            return

        if requested_already_enabled and state.is_paused:
            await message.answer(
                "Эта подписка уже включена, но рассылка стоит на паузе. Нажмите «Стоп», чтобы продолжить.",
                reply_markup=_build_keyboard(),
            )
            return

        if state.is_paused or not state.is_active:
            new_apartments_enabled = bool(enable_apartments)
            new_commercial_enabled = bool(enable_commercial)
        else:
            new_apartments_enabled = state.apartments_enabled or enable_apartments
            new_commercial_enabled = state.commercial_enabled or enable_commercial
        changed = (
            new_apartments_enabled != state.apartments_enabled
            or new_commercial_enabled != state.commercial_enabled
            or state.is_paused
            or not state.is_active
        )

        if not changed:
            await message.answer(
                "Подписка уже активна.",
                reply_markup=_build_keyboard(),
            )
            return

        await upsert_sale_broadcast_state(
            session,
            **_state_payload(
                user_id=user_id,
                existing=state,
                is_active=new_apartments_enabled or new_commercial_enabled,
                apartments_enabled=new_apartments_enabled,
                commercial_enabled=new_commercial_enabled,
                is_paused=False,
                started_at=state.started_at or now,
                last_batch_at=None,
                pending_ads=[],
            ),
        )

    if new_apartments_enabled and new_commercial_enabled:
        text = (
            f"Подписки на квартиры и коммерцию включены. Отправка идёт из базы каждые "
            f"{SEND_INTERVAL_SECONDS} секунд, от самого старого объявления к новому."
        )
    elif new_apartments_enabled:
        text = (
            f"Подписка на квартиры включена. Отправка идёт из базы каждые "
            f"{SEND_INTERVAL_SECONDS} секунд, от самого старого объявления к новому."
        )
    else:
        text = (
            f"Подписка на коммерцию включена. Отправка идёт из базы каждые "
            f"{SEND_INTERVAL_SECONDS} секунд, от самого старого объявления к новому."
        )

    await message.answer(text, reply_markup=_build_keyboard())
    await send_broadcast_step_for_user(bot=message.bot, user_id=user_id, force=True)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    logger.info("start_handler: from_id=%s username=%s", message.from_user.id, message.from_user.username)
    async with AsyncSessionLocal() as session:
        await upsert_user(session=session, user_id=message.from_user.id, username=message.from_user.username)

    await message.answer(
        "Кнопки работают как подписки на рассылку из базы данных. "
        "Скрапинг запускается командой /start_scraping, а /reset очищает историю уже отправленных объявлений.",
        reply_markup=_build_keyboard(),
    )


@router.message(Command("start_scraping"))
async def start_scraping_handler(message: Message) -> None:
    global _scraping_task
    if _scraping_running():
        await message.answer("Скрапинг уже запущен.", reply_markup=_build_keyboard())
        return

    _scraping_task = asyncio.create_task(_run_scraping_loop())
    await message.answer(
        "Скрапинг запущен: сначала продажа квартир, потом продажа коммерции, потом аренда коммерции.",
        reply_markup=_build_keyboard(),
    )


@router.message(Command("reset"))
async def reset_history_handler(message: Message) -> None:
    user_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        state = await _ensure_broadcast_state(session, user_id=user_id, username=message.from_user.username)
        subscriptions_active = state.apartments_enabled or state.commercial_enabled
        await upsert_sale_broadcast_state(
            session,
            **_state_payload(
                user_id=user_id,
                existing=state,
                is_active=subscriptions_active,
                is_paused=False,
                last_batch_at=None,
                total_found=0,
                pending_ads=[],
                sent_olx_ids=[],
            ),
        )

    await message.answer(
        "История отправленных объявлений очищена. Рассылка начнётся заново с самых старых объявлений по вашим активным подпискам.",
        reply_markup=_build_keyboard(),
    )
    await send_broadcast_step_for_user(bot=message.bot, user_id=user_id, force=True)


@router.message(F.text == APARTMENTS_BUTTON)
async def start_apartments_handler(message: Message) -> None:
    logger.info("apartments_button: from_id=%s", message.from_user.id)
    await _activate_subscription(message=message, enable_apartments=True)


@router.message(F.text == COMMERCIAL_BUTTON)
async def start_commercial_handler(message: Message) -> None:
    logger.info("commercial_button: from_id=%s", message.from_user.id)
    await _activate_subscription(message=message, enable_commercial=True)


@router.message(F.text == STOP_BUTTON)
async def stop_broadcast_handler(message: Message) -> None:
    user_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        state = await _ensure_broadcast_state(session, user_id=user_id, username=message.from_user.username)
        subscriptions_active = state.apartments_enabled or state.commercial_enabled
        if not subscriptions_active:
            await message.answer("Активных подписок пока нет.", reply_markup=_build_keyboard())
            return

        new_paused = not state.is_paused
        await upsert_sale_broadcast_state(
            session,
            **_state_payload(
                user_id=user_id,
                existing=state,
                is_active=True,
                is_paused=new_paused,
                last_batch_at=None if not new_paused else state.last_batch_at,
                pending_ads=[],
            ),
        )

    if new_paused:
        await message.answer("Рассылка поставлена на паузу.", reply_markup=_build_keyboard())
        return

    await message.answer("Рассылка продолжена.", reply_markup=_build_keyboard())
    await send_broadcast_step_for_user(bot=message.bot, user_id=user_id, force=True)


async def main() -> None:
    global _scraping_task
    _setup_logging()

    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in environment (.env)")

    logger.info("Starting bot...")
    await init_db()

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    worker_task = asyncio.create_task(run_worker(bot))
    try:
        await dp.start_polling(bot)
    finally:
        if _scraping_task is not None:
            _scraping_task.cancel()
            try:
                await _scraping_task
            except asyncio.CancelledError:
                pass
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
