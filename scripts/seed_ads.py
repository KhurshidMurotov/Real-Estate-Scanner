"""Скрипт для первоначального заполнения БД объявлениями.

Запуск: python scripts/seed_ads.py
Время работы: 10-15 минут
Не прерывайте — дождитесь сообщения "ИТОГО: Готово!"
"""
import asyncio
import logging
import sys
from pathlib import Path

# Добавляем src в path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from real_estate_scanner.db.crud import add_ad, is_new_ad
from real_estate_scanner.db.init_db import init_db
from real_estate_scanner.db.session import AsyncSessionLocal
from real_estate_scanner.parser.olx_client import build_search_url, enrich_ad_with_details, fetch_ads_from_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Районы для сбора
DISTRICTS = [
    ("sale", "tashkent"),
    ("rent", "tashkent"),
    ("sale", "mirzoulugbek"),
    ("rent", "mirzoulugbek"),
    ("sale", "yunusabadskiy"),
    ("rent", "yunusabadskiy"),
    ("sale", "chilanzarskiy"),
    ("rent", "chilanzarskiy"),
    ("sale", "yakkasarayskiy"),
    ("rent", "yakkasarayskiy"),
]


async def collect_all():
    """Собирает объявления по всем районам."""
    print("=" * 60)
    print("ЗАПОЛНЕНИЕ БАЗЫ ДАННЫХ ДЛЯ ОЦЕНКИ НЕДВИЖИМОСТИ")
    print("=" * 60)
    print(f"Районов для сбора: {len(DISTRICTS)}")
    print(f"Примерное время: 10-15 минут")
    print(f"НЕ ПРЕРЫВАЙТЕ — дождитесь сообщения 'Готово!'")
    print("=" * 60)
    
    await init_db()
    
    total_saved = 0
    total_processed = 0
    
    async with AsyncSessionLocal() as session:
        for idx, (ad_type, district_slug) in enumerate(DISTRICTS, 1):
            print(f"\n[{idx}/{len(DISTRICTS)}] Сбор {ad_type.upper()} {district_slug}...")
            try:
                url = build_search_url(ad_type=ad_type, city_slug=district_slug)
                print(f"  URL: {url[:60]}...")
                
                ads = await fetch_ads_from_search(
                    url=url, 
                    ad_type=ad_type, 
                    city=district_slug, 
                    limit=20
                )
                print(f"  Найдено: {len(ads)} объявлений")
                
                district_saved = 0
                for ad in ads:
                    total_processed += 1
                    
                    # Проверяем есть ли уже
                    if not await is_new_ad(session, ad.olx_id):
                        continue
                    
                    try:
                        # Обогащаем и сохраняем
                        detailed = await enrich_ad_with_details(ad)
                        
                        await add_ad(
                            session=session,
                            ad_data={
                                "olx_id": detailed.olx_id,
                                "ad_type": detailed.ad_type,
                                "price": detailed.price,
                                "link": detailed.link,
                                "title": detailed.title,
                                "image_url": detailed.image_url,
                                "area": detailed.area,
                                "rooms": detailed.rooms,
                                "floor": detailed.floor,
                                "total_floors": detailed.total_floors,
                                "district": detailed.district,
                                "city": detailed.city,
                                "description": detailed.description,
                                "raw_data": {
                                    "olx_id": detailed.olx_id,
                                    "title": detailed.title,
                                    "price": detailed.price,
                                    "link": detailed.link,
                                    "image_url": detailed.image_url,
                                    "rooms": detailed.rooms,
                                    "area": detailed.area,
                                    "ad_type": detailed.ad_type,
                                    "city": detailed.city,
                                    "district": detailed.district,
                                    "floor": detailed.floor,
                                    "total_floors": detailed.total_floors,
                                    "description": detailed.description,
                                    "author_name": getattr(detailed, "author_name", None),
                                    "created_at_text": getattr(detailed, "created_at_text", None),
                                },
                            },
                        )
                        total_saved += 1
                        district_saved += 1
                        print(f"  [+] {detailed.olx_id}: ${detailed.price}, {detailed.area}м², {detailed.rooms}к")
                        
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        logger.debug(f"  Ошибка сохранения {ad.olx_id}: {e}")
                        continue
                        
                print(f"  === Сохранено новых: {district_saved}")
                
            except Exception as e:
                print(f"  [ОШИБКА] {ad_type} {district_slug}: {e}")
                continue
    
    print("\n" + "=" * 60)
    print(f"ИТОГО: Обработано {total_processed}, сохранено новых {total_saved}")
    print("БД готова к использованию для оценки!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(collect_all())
    except KeyboardInterrupt:
        print("\n\n[!] Сбор прерван пользователем (Ctrl+C)")
        print("Запустите снова: python scripts/seed_ads.py")
        sys.exit(1)
