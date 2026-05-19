# -*- coding: utf-8 -*-

import os
import asyncio
import logging
import requests
import urllib3

from flask import Flask
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from aiogram import Bot

# Отключаем предупреждения о небезопасном соединении
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Загружаем .env для локального запуска
if os.path.exists(".env"):
    load_dotenv()

# Логирование
logging.basicConfig(level=logging.INFO)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN:
    raise ValueError("❌ Не найдена переменная окружения BOT_TOKEN")

if not CHAT_ID:
    raise ValueError("❌ Не найдена переменная окружения CHAT_ID")

try:
    CHAT_ID = int(CHAT_ID)
except ValueError:
    raise ValueError("❌ CHAT_ID должен быть числом, например -1001234567890")

# Инициализация Flask
app = Flask(__name__)


@app.route("/")
def home():
    return "Quiz Bot is running", 200


@app.route("/health")
def health():
    return "OK", 200


@app.route("/send")
def send_endpoint():
    """
    Endpoint для cron-job.org.
    Cron-job должен дергать именно этот URL:
    https://quiz-bot-yf88.onrender.com/send

    Важно: возвращаем только короткий ответ OK,
    чтобы не было ошибки 'вывод слишком большой'.
    """
    try:
        asyncio.run(send_quiz_schedule())
        return "OK", 200
    except Exception:
        logging.exception("❌ Ошибка при запуске рассылки через /send")
        return "ERROR", 500


def parse_quiz_schedule():
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        url = "https://findquiz.ru/category/sport"

        response = requests.get(
            url,
            headers=headers,
            timeout=20,
            verify=False,
        )
        response.raise_for_status()
        response.encoding = "utf-8"

        soup = BeautifulSoup(response.text, "html.parser")
        quiz_items = soup.find_all("li", class_="top")

        if not quiz_items:
            return "❌ На сайте не найдено ни одного квиза."

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

        result = "🗓 <b>Расписание спортивных квизов</b>\n\n"
        count = 0
        max_quizzes = 10

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
                    day_digits = "".join(c for c in day_text if c.isdigit())
                    day = day_digits if day_digits else "?"

                month_span = date_box.find("span", class_="date-small-month1")
                if month_span:
                    month = month_span.get_text(strip=True).lower()

            # Время
            time_text = "20:00"
            desc_list = item.find_all("p", class_="desc")

            for p in desc_list:
                p_text = p.get_text(" ", strip=True)

                if "Начало игры" in p_text:
                    time_span = p.find("span", class_="info-text")
                    if time_span:
                        parsed_time = time_span.get_text(strip=True).split()[0]
                        if ":" in parsed_time:
                            time_text = parsed_time
                    break

            formatted_date = f"{day} {month}, {time_text}"

            # Место
            location_link = item.find("a", class_="location-href")
            location = (
                location_link.get_text(strip=True)
                if location_link
                else "Место не указано"
            )

            # Цена
            price_text = "Цена не указана"

            for p in desc_list:
                p_text = p.get_text(" ", strip=True)

                if "Цена" in p_text or "руб" in p_text:
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

            if count >= max_quizzes:
                break

        if count == 0:
            return "❌ Не найдено ни одного квиза на тему «Спорт»."

        result += "⚽ Готов к спортивной баталии?"
        return result

    except requests.RequestException as e:
        logging.exception("Ошибка запроса к findquiz.ru")
        return f"❌ Ошибка при подключении к сайту: {e}"

    except Exception as e:
        logging.exception("Ошибка при парсинге расписания")
        return f"❌ Ошибка при парсинге: {e}"


async def send_quiz_schedule():
    message = parse_quiz_schedule()

    bot = Bot(token=BOT_TOKEN)

    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="HTML",
        )
        logging.info("✅ Сообщение успешно отправлено в Telegram")

    except Exception:
        logging.exception("❌ Не удалось отправить сообщение в Telegram")
        raise

    finally:
        await bot.session.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logging.info(f"🌍 Запускаем веб-сервер на порту {port}")

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True,
    )
