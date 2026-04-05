"""Модуль оценки стоимости недвижимости (Market Comparison Approach)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from real_estate_scanner.db.crud import get_comparable_ads as get_comparable_ads_from_db
from real_estate_scanner.db.session import AsyncSessionLocal
from real_estate_scanner.parser.olx_client import (
    ParsedAd,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValuationParams:
    """Параметры для оценки."""
    ad_type: str  # "sale" или "rent"
    housing_type: str  # "new" или "secondary"
    rooms: int
    area: float
    floor: int
    total_floors: int
    district: str  # slug района
    furnished: bool = False
    bathrooms: Optional[int] = None
    renovation: Optional[str] = None  # "new", "good", "cosmetic", "needs_repair"
    building_year: Optional[int] = None


@dataclass
class ValuationResult:
    """Результат оценки."""
    min_price: int  # минимальная цена ($)
    max_price: int  # максимальная цена ($)
    avg_price_per_sqm: float  # средняя цена за м² ($)
    comparable_ads: list[ParsedAd]  # сравнимые объявления
    confidence: str  # "high", "medium", "low" - насколько много данных
    currency: str = "USD"


# Коэффициенты корректировки (примерные значения)
FLOOR_COEFFICIENTS = {
    "first": 0.95,  # первый этаж дешевле
    "last": 0.97,   # последний этаж чуть дешевле
    "middle": 1.0,  # средние этажи - база
}

RENOVATION_COEFFICIENTS = {
    "new": 1.15,        # новый ремонт
    "good": 1.08,       # хороший
    "cosmetic": 1.0,    # косметический - база
    "needs_repair": 0.85, # требует ремонта
}

FURNISHED_COEFFICIENT = 1.05  # с мебелью дороже
RENT_FURNISHED_COEFFICIENT = 1.15  # для аренды мебель важнее

# Конвертация из сумов в USD (примерный курс, можно обновлять)
UZS_TO_USD_RATE = 0.00008  # 1 сум = ~0.00008 USD (примерно 1 USD = 12,500 сум)


async def fetch_comparable_ads(
    params: ValuationParams,
    limit: int = 20,
) -> list[ParsedAd]:
    """
    Быстрый поиск сравнимых объявлений из локальной БД.
    
    Вместо парсинга OLX "на лету" используем предварительно собранные данные.
    Оценка работает за 0.01 сек вместо 10-15 сек.
    """
    logger.info(
        "Оценка: быстрый поиск из БД district=%s rooms=%s area=%s",
        params.district,
        params.rooms,
        params.area,
    )
    
    try:
        async with AsyncSessionLocal() as session:
            ads_from_db = await get_comparable_ads_from_db(
                session=session,
                ad_type=params.ad_type,
                city=params.district,
                rooms=params.rooms,
                area=params.area,
                limit=limit,
            )
            
            # Конвертируем Ad из БД в ParsedAd для совместимости
            comparable = []
            for ad in ads_from_db:
                comparable.append(
                    ParsedAd(
                        olx_id=ad.olx_id,
                        title=ad.title,
                        price=ad.price,
                        link=ad.link,
                        image_url=ad.image_url,
                        rooms=ad.rooms,
                        area=float(ad.area) if ad.area else None,
                        ad_type=ad.ad_type,
                        city=ad.city or params.district,
                        district=ad.district,
                        floor=ad.floor,
                        total_floors=ad.total_floors,
                        description=ad.description,
                    )
                )
            
            logger.info(
                "Оценка: найдено %s сравнимых объявлений из БД",
                len(comparable),
            )
            return comparable
            
    except Exception as e:
        logger.exception("Оценка: ошибка при поиске из БД: %s", e)
        # Если БД недоступна — возвращаем пустой список
        return []


def calculate_price_per_sqm(ads: list[ParsedAd]) -> list[float]:
    """Вычисляет цену за м² для каждого объявления."""
    prices_per_sqm = []
    
    for ad in ads:
        if ad.area is None or ad.area <= 0:
            continue
            
        # Конвертируем цену из сумов в USD
        price_usd = ad.price * UZS_TO_USD_RATE
        price_per_sqm = price_usd / ad.area
        
        if price_per_sqm > 0:
            prices_per_sqm.append(price_per_sqm)
    
    return prices_per_sqm


def apply_adjustment_coefficients(
    base_price: float,
    params: ValuationParams,
) -> float:
    """Применяет корректирующие коэффициенты к базовой цене."""
    coefficient = 1.0
    
    # Коэффициент этажа
    if params.floor == 1:
        coefficient *= FLOOR_COEFFICIENTS["first"]
    elif params.floor == params.total_floors:
        coefficient *= FLOOR_COEFFICIENTS["last"]
    else:
        coefficient *= FLOOR_COEFFICIENTS["middle"]
    
    # Коэффициент ремонта
    if params.renovation:
        coefficient *= RENOVATION_COEFFICIENTS.get(params.renovation, 1.0)
    
    # Коэффициент меблировки
    if params.furnished:
        if params.ad_type == "rent":
            coefficient *= RENT_FURNISHED_COEFFICIENT
        else:
            coefficient *= FURNISHED_COEFFICIENT
    
    # Коэффициент типа жилья (новостройка дороже вторички)
    if params.housing_type == "new" and params.ad_type == "sale":
        coefficient *= 1.1  # новостройка на 10% дороже
    elif params.housing_type == "secondary" and params.ad_type == "sale":
        coefficient *= 0.95  # вторичка на 5% дешевле
    
    return base_price * coefficient


def calculate_valuation(
    comparable_ads: list[ParsedAd],
    params: ValuationParams,
) -> ValuationResult:
    """
    Вычисляет оценку на основе сравнимых объявлений.
    
    Алгоритм:
    1. Вычисляем цену за м² для каждого объявления
    2. Отбрасываем выбросы (цены за м² выше/ниже 2 ст. отклонений)
    3. Вычисляем среднюю цену за м²
    4. Применяем коэффициенты
    5. Вычисляем диапазон цены для заданной площади
    """
    if not comparable_ads:
        # Нет данных для сравнения
        return ValuationResult(
            min_price=0,
            max_price=0,
            avg_price_per_sqm=0.0,
            comparable_ads=[],
            confidence="low",
        )
    
    prices_per_sqm = calculate_price_per_sqm(comparable_ads)
    
    # Fallback: если нет цен за м² (у объявлений нет area), используем среднюю цену за объявление
    if not prices_per_sqm:
        logger.warning("Оценка: нет данных о площади в объявлениях, используем среднюю цену")
        
        # Берём цены объявлений с тем же количеством комнат
        matching_prices = []
        for ad in comparable_ads:
            if ad.rooms == params.rooms and ad.price > 0:
                matching_prices.append(ad.price)
        
        # Если нет точного совпадения по комнатам - берём все
        if not matching_prices:
            matching_prices = [ad.price for ad in comparable_ads if ad.price > 0]
        
        if matching_prices:
            avg_total_price = sum(matching_prices) / len(matching_prices)
            # Применяем коэффициенты к средней цене
            adjusted_price = apply_adjustment_coefficients(avg_total_price * UZS_TO_USD_RATE, params)
            
            # Диапазон ±20%
            min_price = int(adjusted_price * 0.8)
            max_price = int(adjusted_price * 1.2)
            
            # Приблизительная цена за м²
            avg_price_per_sqm = adjusted_price / params.area if params.area > 0 else 0
            
            confidence = "low" if len(matching_prices) < 5 else "medium"
            
            return ValuationResult(
                min_price=min_price,
                max_price=max_price,
                avg_price_per_sqm=round(avg_price_per_sqm, 2),
                comparable_ads=comparable_ads,
                confidence=confidence,
            )
        
        logger.warning("Оценка: не удалось вычислить цену")
        return ValuationResult(
            min_price=0,
            max_price=0,
            avg_price_per_sqm=0.0,
            comparable_ads=comparable_ads,
            confidence="low",
        )
    
    # Сортируем и отбрасываем выбросы (25-й и 75-й перцентили)
    prices_per_sqm.sort()
    n = len(prices_per_sqm)
    
    if n >= 4:
        # Отбрасываем 10% снизу и сверху
        lower_idx = max(0, int(n * 0.1))
        upper_idx = min(n - 1, int(n * 0.9))
        filtered_prices = prices_per_sqm[lower_idx:upper_idx + 1]
    else:
        filtered_prices = prices_per_sqm
    
    # Вычисляем статистики
    avg_price_per_sqm = sum(filtered_prices) / len(filtered_prices)
    min_price_per_sqm = min(filtered_prices)
    max_price_per_sqm = max(filtered_prices)
    
    # Применяем коэффициенты
    adjusted_avg = apply_adjustment_coefficients(avg_price_per_sqm, params)
    adjusted_min = apply_adjustment_coefficients(min_price_per_sqm, params)
    adjusted_max = apply_adjustment_coefficients(max_price_per_sqm, params)
    
    # Вычисляем цену объекта
    min_price = int(adjusted_min * params.area)
    max_price = int(adjusted_max * params.area)
    
    # Определяем уверенность
    if len(filtered_prices) >= 10:
        confidence = "high"
    elif len(filtered_prices) >= 5:
        confidence = "medium"
    else:
        confidence = "low"
    
    return ValuationResult(
        min_price=min_price,
        max_price=max_price,
        avg_price_per_sqm=round(adjusted_avg, 2),
        comparable_ads=comparable_ads,
        confidence=confidence,
    )


async def estimate_property_value(
    params: ValuationParams,
) -> ValuationResult:
    """
    Главная функция оценки недвижимости.
    
    Args:
        params: Параметры объекта для оценки
        
    Returns:
        Результат оценки с диапазоном цен
    """
    try:
        # Таймаут 15 секунд на сбор данных
        comparable_ads = await asyncio.wait_for(
            fetch_comparable_ads(params),
            timeout=15.0,
        )
        result = calculate_valuation(comparable_ads, params)
        return result
    except asyncio.TimeoutError:
        logger.error("Оценка: таймаут при сборе данных с OLX (15 сек)")
        return ValuationResult(
            min_price=0,
            max_price=0,
            avg_price_per_sqm=0.0,
            comparable_ads=[],
            confidence="low",
        )
    except Exception as e:
        logger.exception("Оценка: ошибка при сборе данных: %s", e)
        return ValuationResult(
            min_price=0,
            max_price=0,
            avg_price_per_sqm=0.0,
            comparable_ads=[],
            confidence="low",
        )


def format_valuation_message(result: ValuationResult, params: ValuationParams) -> str:
    """Форматирует результат оценки для отправки пользователю."""
    
    # Если нет объявлений вообще - показываем ошибку
    if not result.comparable_ads:
        return (
            "📊 *Результат оценки*\n\n"
            "❌ Недостаточно данных для оценки.\n"
            "Найдено объявлений: 0\n\n"
            "💡 *Совет:* Попробуйте выбрать другой район или увеличить диапазон площади."
        )
    
    # Если есть объявления но confidence=low - всё равно показываем оценку (приблизительную)
    if result.confidence == "low" and (result.min_price == 0 or result.max_price == 0):
        return (
            "📊 *Результат оценки*\n\n"
            "⚠️ *Найдено мало данных для точной оценки.*\n"
            f"Найдено объявлений: {len(result.comparable_ads)}\n\n"
            "💡 *Совет:* Для более точной оценки нужно минимум 5 сравнимых объявлений с указанной площадью."
        )
    
    # Определяем эмодзи уверенности
    confidence_emoji = {
        "high": "🟢",
        "medium": "🟡",
        "low": "🔴",
    }.get(result.confidence, "⚪")
    
    # Тип объявления
    ad_type_text = "Продажа" if params.ad_type == "sale" else "Аренда (мес.)"
    
    message = (
        f"📊 *Оценка стоимости: {ad_type_text}*\n\n"
        f"🏠 Параметры:\n"
        f"• {params.rooms} комн., {params.area} м²\n"
        f"• Этаж: {params.floor}/{params.total_floors}\n"
        f"• Район: {params.district}\n"
    )
    
    if params.renovation:
        renovation_names = {
            "new": "Новый ремонт",
            "good": "Хороший ремонт",
            "cosmetic": "Косметический",
            "needs_repair": "Требует ремонта",
        }
        message += f"• Ремонт: {renovation_names.get(params.renovation, params.renovation)}\n"
    
    if params.furnished:
        message += "• С мебелью ✅\n"
    
    message += (
        f"\n💰 *Результат оценки:*\n"
        f"• Минимум: ${result.min_price:,}\n"
        f"• Максимум: ${result.max_price:,}\n"
        f"• Средняя цена за м²: ${result.avg_price_per_sqm:.0f}\n\n"
        f"{confidence_emoji} Надёжность оценки: "
    )
    
    if result.confidence == "high":
        message += "Высокая (10+ объявлений)"
    elif result.confidence == "medium":
        message += "Средняя (5-9 объявлений)"
    else:
        message += "Низкая (<5 объявлений)"
    
    message += f"\n📋 Использовано объявлений: {len(result.comparable_ads)}"
    
    return message
