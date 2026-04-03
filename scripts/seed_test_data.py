"""Заполнение БД тестовыми данными для оценки (обход проблемы с Playwright)."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from real_estate_scanner.db.init_db import init_db
from real_estate_scanner.db.session import AsyncSessionLocal
from real_estate_scanner.db.crud import add_ad

# Тестовые данные объявлений (похожие на реальные с OLX)
TEST_ADS = [
    # Продажа - Ташкент
    {"olx_id": "TEST001", "ad_type": "sale", "price": 450000000, "area": 65, "rooms": 2, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 3, "total_floors": 9},
    {"olx_id": "TEST002", "ad_type": "sale", "price": 520000000, "area": 72, "rooms": 2, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 5, "total_floors": 9},
    {"olx_id": "TEST003", "ad_type": "sale", "price": 680000000, "area": 85, "rooms": 3, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 4, "total_floors": 12},
    {"olx_id": "TEST004", "ad_type": "sale", "price": 380000000, "area": 55, "rooms": 1, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 2, "total_floors": 5},
    {"olx_id": "TEST005", "ad_type": "sale", "price": 750000000, "area": 95, "rooms": 3, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 6, "total_floors": 9},
    
    # Продажа - Юнусабад
    {"olx_id": "TEST006", "ad_type": "sale", "price": 480000000, "area": 68, "rooms": 2, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 3, "total_floors": 12},
    {"olx_id": "TEST007", "ad_type": "sale", "price": 550000000, "area": 75, "rooms": 2, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 7, "total_floors": 12},
    {"olx_id": "TEST008", "ad_type": "sale", "price": 720000000, "area": 90, "rooms": 3, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 8, "total_floors": 16},
    {"olx_id": "TEST009", "ad_type": "sale", "price": 420000000, "area": 60, "rooms": 2, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 2, "total_floors": 9},
    {"olx_id": "TEST010", "ad_type": "sale", "price": 890000000, "area": 110, "rooms": 4, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 10, "total_floors": 16},
    
    # Продажа - Чиланзар
    {"olx_id": "TEST011", "ad_type": "sale", "price": 350000000, "area": 50, "rooms": 1, "district": "Чиланзарский район", "city": "chilanzarskiy", "floor": 1, "total_floors": 5},
    {"olx_id": "TEST012", "ad_type": "sale", "price": 420000000, "area": 65, "rooms": 2, "district": "Чиланзарский район", "city": "chilanzarskiy", "floor": 3, "total_floors": 9},
    {"olx_id": "TEST013", "ad_type": "sale", "price": 580000000, "area": 80, "rooms": 3, "district": "Чиланзарский район", "city": "chilanzarskiy", "floor": 4, "total_floors": 9},
    {"olx_id": "TEST014", "ad_type": "sale", "price": 310000000, "area": 45, "rooms": 1, "district": "Чиланзарский район", "city": "chilanzarskiy", "floor": 5, "total_floors": 5},
    {"olx_id": "TEST015", "ad_type": "sale", "price": 650000000, "area": 88, "rooms": 3, "district": "Чиланзарский район", "city": "chilanzarskiy", "floor": 6, "total_floors": 9},
    
    # Продажа - Яккасарай
    {"olx_id": "TEST016", "ad_type": "sale", "price": 600000000, "area": 70, "rooms": 2, "district": "Яккасарайский район", "city": "yakkasarayskiy", "floor": 2, "total_floors": 5},
    {"olx_id": "TEST017", "ad_type": "sale", "price": 750000000, "area": 85, "rooms": 3, "district": "Яккасарайский район", "city": "yakkasarayskiy", "floor": 3, "total_floors": 7},
    {"olx_id": "TEST018", "ad_type": "sale", "price": 550000000, "area": 62, "rooms": 2, "district": "Яккасарайский район", "city": "yakkasarayskiy", "floor": 4, "total_floors": 5},
    {"olx_id": "TEST019", "ad_type": "sale", "price": 920000000, "area": 105, "rooms": 4, "district": "Яккасарайский район", "city": "yakkasarayskiy", "floor": 5, "total_floors": 7},
    {"olx_id": "TEST020", "ad_type": "sale", "price": 480000000, "area": 58, "rooms": 2, "district": "Яккасарайский район", "city": "yakkasarayskiy", "floor": 1, "total_floors": 4},
    
    # Аренда - Мирзо-Улугбек
    {"olx_id": "TEST021", "ad_type": "rent", "price": 3500000, "area": 65, "rooms": 2, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 3, "total_floors": 9},
    {"olx_id": "TEST022", "ad_type": "rent", "price": 4200000, "area": 72, "rooms": 2, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 5, "total_floors": 9},
    {"olx_id": "TEST023", "ad_type": "rent", "price": 5500000, "area": 85, "rooms": 3, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 4, "total_floors": 12},
    {"olx_id": "TEST024", "ad_type": "rent", "price": 2800000, "area": 55, "rooms": 1, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 2, "total_floors": 5},
    {"olx_id": "TEST025", "ad_type": "rent", "price": 6000000, "area": 95, "rooms": 3, "district": "Мирзо-Улугбекский район", "city": "mirzoulugbek", "floor": 6, "total_floors": 9},
    
    # Аренда - Юнусабад
    {"olx_id": "TEST026", "ad_type": "rent", "price": 3800000, "area": 68, "rooms": 2, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 3, "total_floors": 12},
    {"olx_id": "TEST027", "ad_type": "rent", "price": 4500000, "area": 75, "rooms": 2, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 7, "total_floors": 12},
    {"olx_id": "TEST028", "ad_type": "rent", "price": 5800000, "area": 90, "rooms": 3, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 8, "total_floors": 16},
    {"olx_id": "TEST029", "ad_type": "rent", "price": 3200000, "area": 60, "rooms": 2, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 2, "total_floors": 9},
    {"olx_id": "TEST030", "ad_type": "rent", "price": 7000000, "area": 110, "rooms": 4, "district": "Юнусабадский район", "city": "yunusabadskiy", "floor": 10, "total_floors": 16},
]


async def seed_test_data():
    """Заполняет БД тестовыми данными."""
    print("=" * 60)
    print("ЗАПОЛНЕНИЕ БАЗЫ ТЕСТОВЫМИ ДАННЫМИ")
    print("=" * 60)
    print(f"Объявлений для добавления: {len(TEST_ADS)}")
    print("=" * 60)
    
    await init_db()
    
    async with AsyncSessionLocal() as session:
        saved = 0
        for ad in TEST_ADS:
            try:
                await add_ad(
                    session=session,
                    ad_data={
                        "olx_id": ad["olx_id"],
                        "ad_type": ad["ad_type"],
                        "price": ad["price"],
                        "link": f"https://www.olx.uz/d/obyavlenie/test-{ad['olx_id']}.html",
                        "title": f"{ad['rooms']}-комнатная квартира, {ad['area']} м²",
                        "image_url": None,
                        "area": ad["area"],
                        "rooms": ad["rooms"],
                        "floor": ad["floor"],
                        "total_floors": ad["total_floors"],
                        "district": ad["district"],
                        "city": ad["city"],
                        "description": f"Тестовое объявление для оценки. {ad['rooms']} комнат, {ad['area']} м², этаж {ad['floor']}/{ad['total_floors']}",
                        "raw_data": ad,
                    },
                )
                saved += 1
                print(f"[+] {ad['olx_id']}: {ad['ad_type']}, {ad['district']}, {ad['rooms']}к, {ad['area']}м², {ad['price']} сум")
            except Exception as e:
                print(f"[!] Ошибка {ad['olx_id']}: {e}")
    
    print("\n" + "=" * 60)
    print(f"ГОТОВО: Сохранено {saved} из {len(TEST_ADS)} объявлений")
    print("БД готова к тестированию оценки!")
    print("=" * 60)
    print("\nТеперь можно тестировать оценку в боте.")
    print("Данные реалистичны и основаны на средних ценах Ташкента.")


if __name__ == "__main__":
    asyncio.run(seed_test_data())
