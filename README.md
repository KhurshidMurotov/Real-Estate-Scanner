# Real-Estate-Scanner

## Requirements

- Python 3.12
- PostgreSQL
- Playwright (для скрейпинга OLX)

## Setup

1. Установите зависимости:
   - `pip install -e .`

2. Настройте `.env` (создайте из `.env.example` и укажите `DATABASE_URL`).

3. Инициализация БД:
   - `python scripts/init_db.py`

## Tests

Run tests:
- `pytest -q`

Если Playwright ещё не установлен в систему:
- `python -m playwright install`

## Run bot

### Information about run bot

- Сборщик запускается автоматически при старте бота.
- Воркер собирает объявления в фоне.

Из корня проекта:
- `python -m real_estate_scanner.bot.main`

## Information gathering

### Information about seed data

- Скрипт `python scripts/seed_real_data.py` парсит 20 объявлений с OLX (продажа и аренда Ташкента) исохранит в БД.

Из корня проекта:
- `python scripts/seed_real_data.py`


# Как работает оценка
Оценка недвижимости работает по алгоритму Market Comparison Approach:

> [!NOTE]
> ### Что реализовано:
> * **Сбор данных** — бот парсит 20+ похожих объявлений с OLX (тот же район, комнаты ±1, площадь ±20%)
> * **Фильтрация выбросов** — отбрасывает аномальные цены (10% снизу и сверху)
> * **Коэффициенты корректировки:**
>     * Этаж: первый -5%, последний -3%, средние — база
>     * Ремонт: новый +15%, хороший +8%, требует ремонта -15%
>     * Мебель: продажа +5%, аренда +15%
>     * Новостройка vs вторичка
> * **Результат** — диапазон цен ($) с указанием надёжности оценки
