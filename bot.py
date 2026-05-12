import os
import asyncio
import requests
from bs4 import BeautifulSoup
from aiogram import Bot
import schedule
import time
import logging
import urllib3
import threading
from flask import Flask
from dotenv import load_dotenv

# Отключаем предупреждения о небезопасном соединении
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Загружаем .env, если файл существует — нужно для локального запуска
if os.path.exists(".env"):
    load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получаем токен и ID из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if BOT_TOKEN is None:
    raise ValueError("❌ Не найдена переменная окружения BOT_TOKEN. Проверь .env или Environment Variables в Render")

CHAT_ID = os.getenv("CHAT_ID")
if CHAT_ID is None:
    raise ValueError("❌ Не найдена переменная окружения CHAT_ID. Проверь .env или Environment Variables в Render")

try:
    CHAT_ID = int(CHAT_ID)
except ValueError:
    raise ValueError("❌ CHAT_ID должен быть числом, например -1001234567890")

if not BOT_TOKEN.strip():
    raise ValueError("❌ BOT_TOKEN пустой")

# Инициализация бота
bot = Bot(token=BOT_TOKEN)

# Flask-приложение для Render
app = Flask(__name__)


@app.route("/")
def home():
    return "Quiz Bot is running", 200


@app.route("/health")
def health():
    return "OK", 200


def parse_quiz_schedule():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        url = "https://findquiz.ru/category/sport"
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()
        response.encoding = "utf-8"

        soup = BeautifulSoup(response.text, "html.parser")
        quiz_items = soup.find_all("li", class_="top")

        if not quiz_items:
            return "❌ На сайте не найдено ни одного квиза."

        result = "🗓 <b>Расписание спортивных квизов</b>\n\n"

        count = 0
        MAX_QUIZZES = 10

        search_words = [
            "футбол",
            "спорт",
            "хоккей",
            "теннис",
            "баскетбол",
            "волейбол",
            "олимпиада",
            "чемпионат",
            "турнир",
        ]

        for item in quiz_items:
            # Название
            title_h2 = item.find("h2", class_="title")
            if not title_h2:
                continue

            name = title_h2.get_text(strip=True)

            # Организатор
            org_span = item.find("span", class_="org")
            org = org_span.get_text(strip=True) if org_span else "Не указан"

            # Дата
            day = "?"
            month = "???"

            date_box = item.find("div", class_="date-small-box")
            if date_box:
                day_span = date_box.find("span", class_="date-small-date")
                if day_span:
                    day_text = day_span.get_text(strip=True)
                    day = "".join([c for c in day_text if c.isdigit()])
                    if not day:
                        day = "??"

                month_span = date_box.find("span", class_="date-small-month1")
                if month_span:
                    month = month_span.get_text(strip=True).lower()

            # Время
            time_text = "20:00"
            time_p_list = item.find_all("p", class_="desc")

            for p in time_p_list:
                if "Начало игры" in p.get_text():
                    time_span = p.find("span", class_="info-text")
                    if time_span:
                        t = time_span.get_text(strip=True)
                        t = t.split()[0]
                        if ":" in t:
                            time_text = t
                    break

            formatted_date = f"{day} {month}, {time_text}"

            # Место
            location_link = item.find("a", class_="location-href")
            location = location_link.get_text(strip=True) if location_link else "Место не указано"

            # Цена
            price_text = "Цена не указана"

            for p in time_p_list:
                if "Цена" in p.get_text() or "руб" in p.get_text():
                    price_span = p.find("span", class_="info-text")
                    if price_span:
                        price_text = price_span.get_text(strip=True)
                        break

            # Фильтр по спортивной теме
            search_text = f"{name} {org} {location}".lower()
            if not any(word in search_text for word in search_words):
                continue

            count += 1

            result += f"<b>{count}. {name}</b>\n"
            result += f"🏢 Организатор: {org}\n"
            result += f"📅 {formatted_date}\n"
            result += f"📍 {location}\n"
            result += f"💰 {price_text}\n\n"

            if count >= MAX_QUIZZES:
                break

        if count == 0:
            return "❌ Не найдено ни одного квиза на тему «Спорт»."

        result += "⚽ Готов к спортивной баталии?"
        return result

    except Exception as e:
        return f"❌ Ошибка при парсинге: {str(e)}"


async def send_quiz_schedule():
    message = parse_quiz_schedule()

    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="HTML",
        )
        print("✅ Сообщение успешно отправлено в Telegram!")
    except Exception as e:
        print(f"❌ Не удалось отправить сообщение: {e}")


def run_scheduler():
    # Отправка каждый понедельник в 10:00
    schedule.every().monday.at("10:00").do(lambda: asyncio.run(send_quiz_schedule()))

    while True:
        schedule.run_pending()
        time.sleep(1)


def start_bot():
    time.sleep(5)
    print("🤖 Бот запущен. Рассылка — каждый понедельник в 10:00.")

    # Если хочешь, чтобы бот отправлял сообщение сразу при каждом запуске Render,
    # раскомментируй блок ниже.
    #
    # print("📤 Отправляю первое сообщение СРАЗУ...")
    # try:
    #     asyncio.run(send_quiz_schedule())
    # except Exception as e:
    #     print(f"❌ Ошибка при первой отправке: {e}")

    print("⏰ Планировщик запущен...")
    run_scheduler()


if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    # Основной процесс — Flask-сервер для Render
    port = int(os.getenv("PORT", 10000))
    print(f"🌍 Запускаем веб-сервер на порту {port}")

    app.run(host="0.0.0.0", port=port, threaded=True)
