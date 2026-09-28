# -*- coding: utf-8 -*-

import os
import asyncio
import logging
import requests
import urllib3
from datetime import datetime

from flask import Flask, jsonify
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



def fetch_quiz_events():
    """Возвращает структурированное расписание спортивных квизов."""
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

    response = requests.get(
        "https://findquiz.ru/category/sport",
        headers=headers,
        timeout=25,
        verify=False,
    )
    response.raise_for_status()
    response.encoding = "utf-8"

    soup = BeautifulSoup(response.text, "html.parser")
    quiz_items = soup.find_all("li", class_="top")
    events = []

    for item in quiz_items:
        title_h2 = item.find("h2", class_="title")
        if not title_h2:
            continue

        name = title_h2.get_text(strip=True)
        org_span = item.find("span", class_="org")
        org = org_span.get_text(strip=True) if org_span else "Не указан"

        event_url = None
        url_link = item.find("link", attrs={"itemprop": "url"})
        if url_link and url_link.get("href"):
            event_url = url_link["href"]
        if not event_url:
            info_link = item.find("a", class_="info-link")
            if info_link and info_link.get("href"):
                event_url = info_link["href"]

        event_date = None
        time_text = "20:00"
        start_meta = item.find("meta", attrs={"itemprop": "startDate"})
        if start_meta and start_meta.get("content"):
            try:
                start_dt = datetime.fromisoformat(
                    start_meta["content"].replace("Z", "+00:00")
                )
                event_date = start_dt.date().isoformat()
                time_text = start_dt.strftime("%H:%M")
            except ValueError:
                pass

        day = "?"
        weekday = ""
        month = "???"
        date_box = item.find("div", class_="date-small-box")
        if date_box:
            day_span = date_box.find("span", class_="date-small-date")
            if day_span:
                raw_day = day_span.get_text(" ", strip=True)
                digits = "".join(char for char in raw_day if char.isdigit())
                day = digits or "?"
                letters = "".join(char for char in raw_day if char.isalpha()).upper()
                weekday = letters

            month_span = date_box.find("span", class_="date-small-month1")
            if month_span:
                month = month_span.get_text(strip=True).lower()

        desc_list = item.find_all("p", class_="desc")
        for paragraph in desc_list:
            if "Начало игры" not in paragraph.get_text(" ", strip=True):
                continue
            time_span = paragraph.find("span", class_="info-text")
            if time_span:
                parsed_time = time_span.get_text(strip=True).split()[0]
                if ":" in parsed_time:
                    time_text = parsed_time
            break

        location_link = item.find("a", class_="location-href")
        location = (
            location_link.get_text(strip=True)
            if location_link
            else "Место не указано"
        )

        price_text = "Цена не указана"
        for paragraph in desc_list:
            paragraph_text = paragraph.get_text(" ", strip=True)
            if "Цена" not in paragraph_text and "руб" not in paragraph_text:
                continue
            price_span = paragraph.find("span", class_="info-text")
            if price_span:
                price_text = price_span.get_text(strip=True)
            break

        events.append(
            {
                "name": name,
                "org": org,
                "event_date": event_date,
                "day": day,
                "weekday": weekday,
                "month": month,
                "time": time_text,
                "location": location,
                "price": price_text,
                "event_url": event_url,
            }
        )

    if not events:
        raise RuntimeError("На FindQuiz не найдено ни одного спортивного квиза")

    return events


@app.route("/events")
def events_endpoint():
    """JSON API для PDMB-бота на VDS."""
    try:
        events = fetch_quiz_events()
        return jsonify(
            {
                "ok": True,
                "source": "findquiz.ru/category/sport",
                "count": len(events),
                "events": events,
            }
        ), 200
    except Exception as error:
        logging.exception("❌ Ошибка при формировании /events")
        return jsonify({"ok": False, "error": str(error), "events": []}), 502

def parse_quiz_schedule():
    try:
        events = fetch_quiz_events()

        result = "🗓 <b>Расписание спортивных квизов</b>\n\n"
        for index, event in enumerate(events[:10], start=1):
            date_part = f"{event['day']} {event['month']}"
            if event.get("weekday"):
                date_part += f", {event['weekday'].lower()}"

            result += f"<b>{index}. {event['name']}</b>\n"
            result += f"🏢 Организатор: {event['org']}\n"
            result += f"📅 {date_part}, {event['time']}\n"
            result += f"📍 {event['location']}\n"
            result += f"💰 {event['price']}\n\n"

        return result + "⚽ Готов к спортивной баталии?"

    except requests.RequestException as error:
        logging.exception("Ошибка запроса к findquiz.ru")
        return f"❌ Ошибка при подключении к сайту: {error}"
    except Exception as error:
        logging.exception("Ошибка при парсинге расписания")
        return f"❌ Ошибка при парсинге: {error}"


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
