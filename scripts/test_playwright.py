"""Тестовый скрипт для проверки работы Playwright."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from playwright.async_api import async_playwright

async def test_playwright():
    print("Запуск теста Playwright...")
    try:
        async with async_playwright() as p:
            print("Playwright инициализирован")
            
            # Пробуем запустить с разными флагами
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
            print("Браузер запущен!")
            
            page = await browser.new_page()
            print("Страница создана")
            
            # Тестовый переход
            await page.goto("https://www.olx.uz/nedvizhimost/kvartiry/prodazha/tashkent/", timeout=30000)
            print(f"Страница загружена! Title: {await page.title()}")
            
            await browser.close()
            print("Тест пройден успешно!")
            return True
            
    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_playwright())
    sys.exit(0 if success else 1)
