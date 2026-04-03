"""Проверка данных в БД."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from real_estate_scanner.db.session import AsyncSessionLocal
from real_estate_scanner.db.crud import get_comparable_ads

async def check():
    async with AsyncSessionLocal() as session:
        ads = await get_comparable_ads(
            session, 
            ad_type='sale', 
            city='mirzoulugbek', 
            rooms=2, 
            area=60, 
            area_range_percent=20, 
            limit=10
        )
        print(f'Найдено: {len(ads)}')
        for a in ads[:5]:
            print(f'{a.olx_id}: {a.rooms}к, {a.area}м², {a.price} сум, {a.city}')

asyncio.run(check())
