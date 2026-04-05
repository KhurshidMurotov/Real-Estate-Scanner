"""Комплексное тестирование парсера, БД и оценки."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from real_estate_scanner.parser.olx_requests import fetch_ads_requests
from real_estate_scanner.db.session import AsyncSessionLocal
from real_estate_scanner.db.crud import get_comparable_ads, add_ad, is_new_ad
from real_estate_scanner.db.init_db import init_db
from real_estate_scanner.parser.worker import _simple_ad_to_parsed_ad


async def test_parser():
    """Тест 1: Проверка парсера requests"""
    print("=" * 60)
    print("ТЕСТ 1: Парсер requests")
    print("=" * 60)
    
    url = "https://www.olx.uz/nedvizhimost/kvartiry/prodazha/tashkent/"
    ads = await fetch_ads_requests(url=url, ad_type="sale", city="tashkent", limit=5)
    
    print(f"Получено объявлений: {len(ads)}")
    for i, ad in enumerate(ads[:3], 1):
        print(f"  {i}. {ad.olx_id}: {ad.rooms}к, {ad.area}м², {ad.price} сум")
    
    return len(ads) > 0


async def test_database():
    """Тест 2: Проверка БД"""
    print("\n" + "=" * 60)
    print("ТЕСТ 2: База данных")
    print("=" * 60)
    
    await init_db()
    print("База данных инициализирована")
    
    async with AsyncSessionLocal() as session:
        ads = await get_comparable_ads(
            session, ad_type="sale", city="mirzoulugbek", rooms=2, area=60, limit=10
        )
        print(f"Найдено сравнимых объявлений: {len(ads)}")
        
        if ads:
            for i, ad in enumerate(ads[:3], 1):
                print(f"  {i}. {ad.olx_id}: {ad.rooms}к, {ad.area}м², {ad.price} сум")
        
        return len(ads) > 0


async def test_full_flow():
    """Тест 3: Полный цикл - парсинг и сохранение"""
    print("\n" + "=" * 60)
    print("ТЕСТ 3: Полный цикл")
    print("=" * 60)
    
    # Парсим
    url = "https://www.olx.uz/nedvizhimost/kvartiry/prodazha/mirzoulugbek/"
    simple_ads = await fetch_ads_requests(url=url, ad_type="sale", city="mirzoulugbek", limit=3)
    
    if not simple_ads:
        print("Не удалось получить объявления")
        return False
    
    print(f"Спарсено: {len(simple_ads)}")
    
    # Сохраняем
    async with AsyncSessionLocal() as session:
        saved = 0
        for simple_ad in simple_ads:
            try:
                is_new = await is_new_ad(session, simple_ad.olx_id)
                if not is_new:
                    print(f"  Пропуск {simple_ad.olx_id} - уже в БД")
                    continue
                
                await add_ad(
                    session=session,
                    ad_data={
                        "olx_id": simple_ad.olx_id,
                        "ad_type": simple_ad.ad_type,
                        "price": simple_ad.price,
                        "link": simple_ad.link,
                        "title": simple_ad.title,
                        "image_url": simple_ad.image_url,
                        "area": simple_ad.area,
                        "rooms": simple_ad.rooms,
                        "floor": None,
                        "total_floors": None,
                        "district": simple_ad.district,
                        "city": simple_ad.city,
                        "description": None,
                        "raw_data": {},
                    },
                )
                saved += 1
                print(f"  Сохранено: {simple_ad.olx_id}")
            except Exception as e:
                print(f"  Ошибка {simple_ad.olx_id}: {e}")
        
        print(f"Сохранено новых: {saved}")
        return saved > 0


async def main():
    print("\n" + "=" * 60)
    print("КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ REAL ESTATE SCANNER")
    print("=" * 60 + "\n")
    
    results = []
    
    try:
        results.append(("Парсер", await test_parser()))
    except Exception as e:
        print(f"ОШИБКА: {e}")
        results.append(("Парсер", False))
    
    try:
        results.append(("База данных", await test_database()))
    except Exception as e:
        print(f"ОШИБКА: {e}")
        results.append(("База данных", False))
    
    try:
        results.append(("Полный цикл", await test_full_flow()))
    except Exception as e:
        print(f"ОШИБКА: {e}")
        results.append(("Полный цикл", False))
    
    print("\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:<20} {status}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\nВсего: {passed}/{total} тестов пройдено")


if __name__ == "__main__":
    asyncio.run(main())
