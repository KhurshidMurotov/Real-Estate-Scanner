"""Альтернативный парсер OLX на requests+BeautifulSoup (без Playwright)."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from real_estate_scanner.config import settings

logger = logging.getLogger(__name__)

# Headers для имитации браузера
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",  # Убран brotli (br)
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class SimpleAd:
    olx_id: str
    ad_type: str
    price: int
    link: str
    title: str
    rooms: int | None
    area: float | None
    city: str
    district: str | None
    image_url: str | None = None


def _extract_price(text: str) -> int:
    """Извлекает цену из текста."""
    # Ищем суммы в формате "XXX XXX XXX сум" или "XXX XXX $"
    sum_match = re.search(r'([\d\s]+)\s*сум', text, re.IGNORECASE)
    if sum_match:
        return int(sum_match.group(1).replace(' ', '').replace('\xa0', ''))
    
    usd_match = re.search(r'([\d\s]+)\s*\$', text)
    if usd_match:
        usd = int(usd_match.group(1).replace(' ', '').replace('\xa0', ''))
        # Конвертируем USD в сум (примерно 1 USD = 12 500 сум)
        return usd * 12500
    
    # Ищем просто числа
    numbers = re.findall(r'\d{7,}', text.replace(' ', '').replace('\xa0', ''))
    if numbers:
        return int(numbers[0])
    
    return 0


def _extract_rooms(text: str) -> int | None:
    """Извлекает количество комнат."""
    patterns = [
        r'(\d+)\s*-\s*комнатная',
        r'(\d+)\s*комнатная',
        r'(\d+)\s*к\.',
        r'(\d+)\s*к\s',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_area(text: str) -> float | None:
    """Извлекает площадь."""
    match = re.search(r'(\d+(?:\.\d+)?)\s*м²', text)
    if match:
        return float(match.group(1))
    return None


def _extract_olx_id(href: str) -> str:
    """Извлекает ID из ссылки OLX."""
    match = re.search(r'/d/obyavlenie/([a-zA-Z0-9_-]+)', href)
    if match:
        return match.group(1)
    # Fallback - используем часть URL
    return href.split('/')[-1].split('_')[0] if '/' in href else href


async def fetch_ads_requests(
    *,
    url: str,
    ad_type: str,
    city: str,
    limit: int = 50,
) -> list[SimpleAd]:
    """Парсит объявления с OLX используя requests+BeautifulSoup."""
    ads: list[SimpleAd] = []
    
    try:
        async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.warning(f"OLX requests: status {response.status} for {url}")
                    return ads
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем карточки объявлений
                # OLX использует разные структуры, пробуем несколько селекторов
                selectors = [
                    '[data-cy="l-card"]',
                    'div[data-testid="listing-grid"] > div',
                    '.css-1sw7qzm',  # старый класс карточки
                    '[class*="card"]',
                    'article',
                ]
                
                cards = []
                for selector in selectors:
                    cards = soup.select(selector)
                    if cards:
                        logger.info(f"OLX requests: found {len(cards)} cards with selector '{selector}'")
                        break
                
                for card in cards[:limit]:
                    try:
                        # Ищем ссылку
                        link_elem = card.find('a', href=True)
                        if not link_elem:
                            continue
                        
                        href = link_elem.get('href', '')
                        if not href.startswith('/d/obyavlenie/'):
                            # Может быть относительная ссылка
                            if 'olx.uz' in href:
                                href = href.split('olx.uz')[-1]
                            else:
                                continue
                        
                        full_link = urljoin(settings.OLX_BASE_URL, href)
                        olx_id = _extract_olx_id(href)
                        
                        # Заголовок
                        title_elem = card.find(['h3', 'h4', 'h5', 'h6', 'p'], class_=True)
                        title = title_elem.get_text(strip=True) if title_elem else "Без названия"
                        
                        # Цена
                        price_elem = card.find(text=re.compile(r'\d+.*(?:сум|\$)'))
                        price_text = price_elem if price_elem else ""
                        price = _extract_price(price_text)
                        if not price:
                            # Ищем в заголовке или тексте карточки
                            price = _extract_price(card.get_text())
                        
                        # Комнаты и площадь
                        card_text = card.get_text()
                        rooms = _extract_rooms(card_text) or _extract_rooms(title)
                        area = _extract_area(card_text) or _extract_area(title)
                        
                        # Картинка
                        img_elem = card.find('img')
                        image_url = img_elem.get('src') if img_elem else None
                        
                        ad = SimpleAd(
                            olx_id=olx_id,
                            ad_type=ad_type,
                            price=price,
                            link=full_link,
                            title=title,
                            rooms=rooms,
                            area=area,
                            city=city,
                            district=None,  # Будет заполнено позже
                            image_url=image_url,
                        )
                        ads.append(ad)
                        
                    except Exception as e:
                        logger.debug(f"Error parsing card: {e}")
                        continue
                
                logger.info(f"OLX requests: parsed {len(ads)} ads from {url}")
                
    except asyncio.TimeoutError:
        logger.error(f"OLX requests: timeout for {url}")
    except Exception as e:
        logger.exception(f"OLX requests: error fetching {url}: {e}")
    
    return ads
