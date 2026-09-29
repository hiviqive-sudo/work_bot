# Схема базы данных

База: SQLite. Доступ: `aiosqlite`.

## 1. users
Хранит Telegram-профиль клиента.

| Поле | Тип | Назначение |
|---|---|---|
| id | INTEGER PK | Telegram ID |
| username | TEXT | username без `@` |
| full_name | TEXT | Имя из Telegram |
| created_at | TEXT | Дата создания записи |
| updated_at | TEXT | Дата последнего обновления |

## 2. services
Справочник услуг мастера.

| Поле | Тип | Назначение |
|---|---|---|
| id | INTEGER PK | ID услуги |
| name | TEXT | Название |
| price | INTEGER | Цена в рублях |
| duration_min | INTEGER | Длительность в минутах |
| is_active | INTEGER | 1 — доступна, 0 — отключена |
| sort_order | INTEGER | Порядок вывода |

## 3. appointments
Записи клиентов.

| Поле | Тип | Назначение |
|---|---|---|
| id | INTEGER PK | ID записи |
| user_id | INTEGER FK | Клиент |
| service_id | INTEGER FK | Услуга |
| appointment_date | TEXT | Дата `YYYY-MM-DD` |
| start_time | TEXT | Начало `HH:MM` |
| end_time | TEXT | Окончание `HH:MM` |
| status | TEXT | Сейчас используются `confirmed` / `cancelled` |
| comment | TEXT | Пожелания клиента |
| created_at | TEXT | Создание |
| updated_at | TEXT | Изменение |
| remind_24_sent | INTEGER | Отправлено ли напоминание за 24 ч |
| remind_2_sent | INTEGER | Отправлено ли напоминание за 2 ч |
| review_requested | INTEGER | Отправлен ли запрос отзыва |

Защита от дублей: уникальный частичный индекс на `(appointment_date, start_time)` для `status='confirmed'`, плюс проверка пересечений и буфера внутри транзакции.

## 4. blocked_times
Временные интервалы, которые мастер закрыл для записи.

Поля: `id`, `block_date`, `start_time`, `end_time`, `reason`, `created_at`.

## 5. waiting_list
Заявки в листе ожидания.

Поля: `id`, `user_id`, `service_id`, `preferred_date`, `created_at`, `notified_at`, `status`.

Статусы: `active`, `notified`, `cancelled`.

## 6. reviews
Отзывы после визита.

| Поле | Тип | Назначение |
|---|---|---|
| id | INTEGER PK | ID отзыва |
| appointment_id | INTEGER UNIQUE FK | Какая запись |
| user_id | INTEGER FK | Клиент |
| rating | INTEGER | 1–5 |
| text | TEXT | Текст |
| created_at | TEXT | Время отзыва |

Уникальность `appointment_id` не позволяет оставить два отзыва к одной записи.

## 7. blacklist
Чёрный список.

Поля: `user_id` PK/FK, `reason`, `created_at`.

## Связи

```text
users 1 ───── N appointments N ───── 1 services
users 1 ───── N waiting_list N ───── 1 services
users 1 ───── N reviews 1 ────────── 1 appointments
users 1 ───── 1 blacklist
```

Дополнительно расписание не хранится в отдельной таблице: рабочие дни, часы, обед и буфер задаются в `config.py`. Доступные слоты рассчитываются динамически на основе этих настроек, записей и блокировок.
