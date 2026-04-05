# 🏠 Real Estate Scanner

> Telegram-бот + Mini App для поиска и оценки недвижимости в Ташкенте

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue?logo=postgresql)](https://postgresql.org)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-blue)](https://docs.aiogram.dev/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

## ✨ Возможности

- 🔍 **Поиск объявлений** — автоматический мониторинг OLX
- 💰 **Оценка стоимости** — расчёт цены на основе аналогов
- 🔔 **Уведомления** — мгновенные оповещения о новых объявлениях
- 📱 **Mini App** — удобный интерфейс в Telegram

## 📋 Требования

| Компонент | Версия |
|-----------|--------|
| Python | 3.12+ |
| PostgreSQL | 15+ |
| Playwright | 1.40+ |

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install -e .
playwright install
```

### 2. Настройка окружения

```bash
cp .env.example .env
# Отредактируйте .env и укажите:
# - DATABASE_URL
# - BOT_TOKEN
# - OLX_BASE_URL
```

### 3. Инициализация базы данных

```bash
python scripts/init_db.py
```

### 4. Заполнение тестовыми данными (опционально)

```bash
python scripts/seed_real_data.py
```

## 🤖 Запуск бота

```bash
python -m real_estate_scanner.bot.main
```

> 💡 **Примечание:** Сборщик данных запускается автоматически в фоновом режиме.

## 🧪 Тестирование

```bash
pytest -q
```

## 📊 Как работает оценка

Оценка недвижимости выполняется по методу **Market Comparison Approach**:

### 📈 Алгоритм

1. **Сбор данных** — поиск 20+ похожих объявлений
   - Тот же район
   - Комнаты ±1 от запрошенных
   - Площадь ±20% от запрошенной

2. **Фильтрация выбросов** — отбрасываются аномальные цены (10% снизу и сверху)

3. **Корректирующие коэффициенты**

| Фактор | Влияние |
|--------|---------|
| 🏢 **Этаж** | Первый -5%, последний -3%, средние — база |
| 🎨 **Ремонт** | Новый +15%, хороший +8%, косметический база, требует ремонта -15% |
| 🛋️ **Мебель** | Продажа +5%, аренда +15% |
| 🆕 **Тип жилья** | Новостройка +10%, вторичка -5% |

4. **Результат** — диапазон цен в **$** с указанием надёжности:
   - 🟢 Высокая (10+ объявлений)
   - 🟡 Средняя (5-9 объявлений)
   - 🔴 Низкая (<5 объявлений)

## 📝 Скрипты

| Скрипт | Описание |
|--------|----------|
| `scripts/init_db.py` | Инициализация базы данных |
| `scripts/seed_real_data.py` | Заполнение БД реальными объявлениями с OLX |
| `scripts/seed_test_data.py` | Генерация тестовых данных |
| `scripts/test_full_system.py` | Комплексное тестирование системы |

## 🏗️ Архитектура

```
Real-Estate-Scanner/
├── 📁 src/real_estate_scanner/
│   ├── 📁 bot/          # Telegram-бот (Aiogram 3)
│   ├── 📁 db/           # Модели и работа с БД (SQLAlchemy)
│   ├── 📁 parser/       # Парсеры OLX (requests + BeautifulSoup)
│   └── 📁 valuation/    # Модуль оценки стоимости
├── 📁 scripts/          # Вспомогательные скрипты
├── 📁 tests/            # Тесты (pytest)
├── 📄 index.html        # Telegram Mini App
└── 📄 valuation.html    # Страница оценки
```

## 📄 Лицензия

MIT License — см. файл [LICENSE](LICENSE)

---

<p align="center">
  Сделано с ❤️ для рынка недвижимости Ташкента
</p>
