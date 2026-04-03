from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from real_estate_scanner.db.models import Ad, Filter, SaleBroadcastState, User

logger = logging.getLogger(__name__)


async def upsert_user(session: AsyncSession, user_id: int, username: str | None) -> None:
    """
    Добавляет пользователя в `users`.
    Если пользователь уже существует — обновляет `username`.
    """
    try:
        stmt = (
            pg_insert(User)
            .values(id=user_id, username=username)
            .on_conflict_do_update(
                index_elements=[User.id],
                set_={"username": username},
            )
        )
        await session.execute(stmt)
        await session.commit()
    except Exception:
        logger.exception("upsert_user failed (user_id=%s)", user_id)
        await session.rollback()
        raise


async def save_filter(session: AsyncSession, user_id: int, filter_data: dict[str, Any]) -> None:
    """
    Сохраняет фильтр пользователя.

    Реализация "один активный фильтр на пользователя":
    - удаляем старый фильтр пользователя
    - вставляем только один новый актуальный фильтр
    """
    try:
        additional_params = filter_data.get("additional_params") or {}
        cities = list(filter_data.get("cities") or [])
        rooms = list(filter_data.get("rooms") or [])

        await session.execute(delete(Filter).where(Filter.user_id == user_id))

        stmt = (
            pg_insert(Filter)
            .values(
                user_id=user_id,
                type=filter_data.get("type"),
                region=filter_data.get("region"),
                cities=cities,
                rooms=rooms,
                price_min=filter_data.get("price_min"),
                price_max=filter_data.get("price_max"),
                area_min=filter_data.get("area_min"),
                area_max=filter_data.get("area_max"),
                additional_params=additional_params,
            )
        )
        await session.execute(stmt)
        await session.commit()
    except Exception:
        logger.exception("save_filter failed (user_id=%s filter_data_keys=%s)", user_id, list(filter_data.keys()))
        await session.rollback()
        raise


async def is_new_ad(session: AsyncSession, olx_id: str) -> bool:
    """Возвращает True, если объявления с `olx_id` ещё нет в таблице `ads`."""
    try:
        stmt = select(Ad.id).where(Ad.olx_id == olx_id).limit(1)
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is None
    except Exception:
        logger.exception("is_new_ad failed (olx_id=%s)", olx_id)
        await session.rollback()
        raise


async def add_ad(session: AsyncSession, ad_data: dict[str, Any]) -> None:
    """
    Сохраняет объявление в `ads` с полными данными для оценки.

    Используем `ON CONFLICT DO UPDATE` по `olx_id`, чтобы обновлять данные если объявление уже есть.
    """
    try:
        values: dict[str, Any] = {
            "olx_id": ad_data["olx_id"],
            "ad_type": ad_data.get("ad_type", "sale"),
            "price": ad_data["price"],
            "link": ad_data["link"],
            "title": ad_data["title"],
        }

        # Опциональные поля
        optional_fields = [
            "area", "rooms", "floor", "total_floors",
            "district", "city", "image_url", "description", "raw_data"
        ]
        for field in optional_fields:
            if field in ad_data:
                values[field] = ad_data[field]

        if "timestamp" in ad_data and ad_data["timestamp"] is not None:
            values["timestamp"] = ad_data["timestamp"]

        stmt = (
            pg_insert(Ad)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Ad.olx_id],
                set_={
                    "price": values["price"],
                    "title": values["title"],
                    "area": values.get("area"),
                    "rooms": values.get("rooms"),
                    "floor": values.get("floor"),
                    "total_floors": values.get("total_floors"),
                    "district": values.get("district"),
                    "city": values.get("city"),
                    "image_url": values.get("image_url"),
                    "description": values.get("description"),
                    "raw_data": values.get("raw_data", {}),
                    "timestamp": values.get("timestamp"),
                },
            )
        )
        await session.execute(stmt)
        await session.commit()
    except Exception:
        logger.exception("add_ad failed (olx_id=%s)", ad_data.get("olx_id"))
        await session.rollback()
        raise


async def get_comparable_ads(
    session: AsyncSession,
    ad_type: str,
    city: str,
    rooms: int,
    area: float,
    limit: int = 20,
) -> list[Ad]:
    """
    Быстрый поиск сравнимых объявлений из локальной БД для оценки.

    Фильтры:
    - Тот же тип (sale/rent)
    - Тот же город/район (city slug)
    - Комнаты: точное совпадение или ±1
    - Площадь ±20% от заданной
    - Данные не старше 7 дней
    """
    from datetime import datetime, timedelta
    from decimal import Decimal

    try:
        area_min = Decimal(str(area * 0.8))
        area_max = Decimal(str(area * 1.2))
        rooms_min = rooms - 1
        rooms_max = rooms + 1
        cutoff_time = datetime.utcnow() - timedelta(days=7)

        stmt = (
            select(Ad)
            .where(
                Ad.ad_type == ad_type,
                Ad.city == city,
                Ad.rooms >= rooms_min,
                Ad.rooms <= rooms_max,
                Ad.area >= area_min,
                Ad.area <= area_max,
                Ad.timestamp >= cutoff_time,
            )
            .order_by(Ad.timestamp.desc())
            .limit(limit)
        )

        res = await session.execute(stmt)
        return list(res.scalars().all())
    except Exception:
        logger.exception(
            "get_comparable_ads failed (type=%s city=%s rooms=%s area=%s)",
            ad_type,
            city,
            rooms,
            area,
        )
        await session.rollback()
        raise


async def get_users_for_ad(
    session: AsyncSession,
    ad_price: int,
    ad_rooms: int,
    ad_area: float | None,
    ad_type: str,
    ad_city: str,
) -> list[int]:
    """
    Ищет пользователей, у которых фильтр совпадает с новым объявлением.

    Возвращает список `users.id`.
    """
    try:
        # Numeric(12,2) в БД, поэтому удобно передавать Decimal.
        area = Decimal(str(ad_area)) if ad_area is not None else None
        stmt = select(User.id, Filter).join(Filter, Filter.user_id == User.id).where(Filter.type == ad_type)
        res = await session.execute(stmt)

        matched_user_ids: list[int] = []
        for user_id, flt in res.all():
            filter_cities = list(flt.cities or [])
            filter_rooms = list(flt.rooms or [])

            city_ok = not filter_cities or ad_city in filter_cities
            rooms_ok = not filter_rooms or ad_rooms in filter_rooms
            price_ok = (flt.price_min is None or flt.price_min <= ad_price) and (
                flt.price_max is None or flt.price_max >= ad_price
            )
            area_ok = True
            if area is not None:
                area_ok = (flt.area_min is None or flt.area_min <= area) and (
                    flt.area_max is None or flt.area_max >= area
                )

            if city_ok and rooms_ok and price_ok and area_ok:
                matched_user_ids.append(user_id)

        return matched_user_ids
    except Exception:
        logger.exception(
            "get_users_for_ad failed (price=%s rooms=%s area=%s type=%s city=%s)",
            ad_price,
            ad_rooms,
            ad_area,
            ad_type,
            ad_city,
        )
        await session.rollback()
        raise


async def get_sale_broadcast_state(session: AsyncSession, user_id: int) -> SaleBroadcastState | None:
    stmt = select(SaleBroadcastState).where(SaleBroadcastState.user_id == user_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def upsert_sale_broadcast_state(
    session: AsyncSession,
    *,
    user_id: int,
    is_active: bool,
    started_at,
    window_start,
    window_end,
    last_batch_at,
    total_found: int,
    pending_ads: list[dict[str, Any]],
    sent_olx_ids: list[str],
) -> None:
    stmt = (
        pg_insert(SaleBroadcastState)
        .values(
            user_id=user_id,
            is_active=is_active,
            started_at=started_at,
            window_start=window_start,
            window_end=window_end,
            last_batch_at=last_batch_at,
            total_found=total_found,
            pending_ads=pending_ads,
            sent_olx_ids=sent_olx_ids,
        )
        .on_conflict_do_update(
            index_elements=[SaleBroadcastState.user_id],
            set_={
                "is_active": is_active,
                "started_at": started_at,
                "window_start": window_start,
                "window_end": window_end,
                "last_batch_at": last_batch_at,
                "total_found": total_found,
                "pending_ads": pending_ads,
                "sent_olx_ids": sent_olx_ids,
            },
        )
    )
    await session.execute(stmt)
    await session.commit()


async def list_active_sale_broadcast_states(session: AsyncSession) -> list[SaleBroadcastState]:
    stmt = select(SaleBroadcastState).where(SaleBroadcastState.is_active.is_(True))
    res = await session.execute(stmt)
    return list(res.scalars().all())

