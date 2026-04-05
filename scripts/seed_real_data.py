"""Заполнение БД реальными объявлениями с OLX (requests-парсер)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from real_estate_scanner.parser.olx_requests import fetch_ads_requests
from real_estate_scanner.db.session import AsyncSessionLocal
from real_estate_scanner.db.crud import add_ad, is_new_ad
from real_estate_scanner.db.init_db import init_db

# Районы Ташкента для сбора
DISTRICTS = [
    ("sale", "tashkent"),
    ("rent", "tashkent"),
]

LIMIT = 20  # Объявлений с каждого URL


async def seed_database():
    """Заполняет БД реальными объявлениями с OLX."""
    print("=" * 60)
    print("ЗАПОЛНЕНИЕ БД РЕАЛЬНЫМИ ДАННЫМИ")
    print("=" * 60)
    
    await init_db()
    print("✓ База данных инициализирована\n")
    
    total_saved = 0
    total_processed = 0
    
    for ad_type, district in DISTRICTS:
        if ad_type == "sale":
            url = f"https://www.olx.uz/nedvizhimost/kvartiry/prodazha/{district}/"
        else:
            url = f"https://www.olx.uz/nedvizhimost/kvartiry/arenda-dolgosrochnaya/{district}/"
        
        print(f"[СБОР] {ad_type} {district}")
        print(f"  URL: {url}")
        
        try:
            ads = await fetch_ads_requests(url=url, ad_type=ad_type, city=district, limit=LIMIT)
            print(f"  Получено: {len(ads)} объявлений")
            
            async with AsyncSessionLocal() as session:
                saved_for_district = 0
                
                for ad in ads:
                    total_processed += 1
                    
                    try:
                        # Проверяем есть ли уже
                        if not await is_new_ad(session, ad.olx_id):
                            print(f"    Пропуск {ad.olx_id} - уже в БД")
                            continue
                        
                        # Сохраняем
                        await add_ad(
                            session=session,
                            ad_data={
                                "olx_id": ad.olx_id,
                                "ad_type": ad.ad_type,
                                "price": ad.price,
                                "link": ad.link,
                                "title": ad.title,
                                "image_url": ad.image_url,
                                "area": ad.area,
                                "rooms": ad.rooms,
                                "floor": None,
                                "total_floors": None,
                                "district": ad.district,
                                "city": ad.city,
                                "description": None,
                                "raw_data": {},
                            },
                        )
                        
                        saved_for_district += 1
                        total_saved += 1
                        print(f"    ✓ Сохранено: {ad.olx_id} ({ad.rooms}к, {ad.area}м², {ad.price} сум)")
                        
                        # Небольшая задержка
                        await asyncio.sleep(0.2)
                        
                    except Exception as e:
                        print(f"    ✗ Ошибка сохранения {ad.olx_id}: {e}")
                        continue
                
                print(f"  Сохранено новых: {saved_for_district}\n")
                
        except Exception as e:
            print(f"  ✗ Ошибка сбора: {e}\n")
            continue
    
    print("=" * 60)
    print("ИТОГИ")
    print("=" * 60)
    print(f"Всего обработано: {total_processed}")
    print(f"Сохранено новых: {total_saved}")
    
    if total_saved > 0:
        print(f"\n✓ БД успешно заполнена! Теперь оценка будет работать.")
    else:
        print(f"\n⚠ Новых объявлений не найдено (возможно, все уже в БД)")


if __name__ == "__main__":
    asyncio.run(seed_database())
