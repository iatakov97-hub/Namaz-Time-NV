# 🕌 Бот времён намазов — Нижневартовск

Telegram-бот с расписанием намазов и уведомлениями.

## Файлы проекта

```
prayer_bot/
├── bot.py                              # основной код бота
├── prayer_times_nizhnevartovsk.csv     # расписание намазов
├── requirements.txt                    # зависимости
├── Procfile                            # для Railway
└── README.md
```

## Деплой на Railway

### 1. Подготовка GitHub

1. Создай новый репозиторий на [github.com](https://github.com)
2. Загрузи все 4 файла: `bot.py`, `prayer_times_nizhnevartovsk.csv`, `requirements.txt`, `Procfile`

### 2. Деплой на Railway

1. Зайди на [railway.app](https://railway.app) → Sign in with GitHub
2. Нажми **New Project** → **Deploy from GitHub repo**
3. Выбери свой репозиторий
4. После деплоя перейди в **Variables** и добавь:
   - `BOT_TOKEN` = твой токен от BotFather

### 3. Запуск

В разделе **Settings** убедись что тип сервиса — **Worker** (не Web).
Railway автоматически запустит бота.

## Локальный запуск

```bash
pip install -r requirements.txt
BOT_TOKEN=ваш_токен python bot.py
```

## Команды бота

| Команда | Описание |
|---------|----------|
| /start | Главное меню |
| /today | Намазы на сегодня |
| /next | До следующего намаза |
| /month | Расписание на месяц |
| /notifications | Настройки уведомлений |

## Уведомления

- 🔔 При наступлении каждого намаза
- ⏰ За 15 минут до окончания времени намаза  
- 🕌 Напоминание о Джума каждую пятницу в 12:00
- Можно включать/выключать по отдельным намазам
