import html
import unittest
from datetime import date
from unittest.mock import patch

from telegram_events import fetch_channel_events, parse_channel_page


def post(channel: str, number: int, published: str, text: str) -> str:
    body = "<br>".join(html.escape(line) for line in text.splitlines())
    return (
        f'<div class="tgme_widget_message" data-post="{channel}/{number}">'
        f'<time datetime="{published}"></time>'
        f'<div class="tgme_widget_message_text">{body}</div></div>'
    )


class Response:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


class TelegramEventsTests(unittest.TestCase):
    def test_quiz_pub_rangers_football_game_and_jersey_price(self):
        page = post(
            "quizpubrangers", 226, "2026-11-07T05:45:16+00:00",
            "🎄 Долгожданный футбольный квиз уже скоро!\n"
            "📅 21 ноября 2026 (суббота)\n"
            "🕓 Начало — 16:30, сбор гостей с 16:00\n"
            "📍 Suckin' Diesel Pub\n"
            "🎟 Вход: 500₽ без джерси / 300₽ в клубной джерси",
        ) + post(
            "quizpubrangers", 237, "2026-11-10T06:41:50+00:00",
            "Призы вручим на квизе 21 ноября. До встречи!",
        )
        with patch("telegram_events.requests.get", return_value=Response(page)):
            events = fetch_channel_events("quizpubrangers", date(2026, 11, 10))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_date"], "2026-11-21")
        self.assertEqual(events[0]["time"], "16:30")
        self.assertEqual(events[0]["location"], "Suckin' Diesel Pub")
        self.assertEqual(events[0]["price"], "500 руб./чел. (300 руб. в клубной джерси)")
        self.assertEqual(events[0]["event_url"], "https://t.me/quizpubrangers/226")

    def test_full_announcement_beats_discount_reminder(self):
        page = post(
            "quizplusmsk", 5280, "2026-10-29T18:18:51+00:00",
            "НОВЫЙ «КВИЗ ПЛЮС»! 9 НОЯБРЯ! КЧАУ\n"
            "Футбольный квиз. Собирайте команду и записывайтесь.\n"
            "📅 9 ноября\n🏟 Chesterfield | Новый Арбат, 19\n"
            "⌚ Начало в 19:30\nСтандартный билет по предоплате стоит 1000 рублей",
        ) + post(
            "quizplusmsk", 5287, "2026-11-01T12:19:51+00:00",
            "Чтобы попасть на игру 9 ноября, запишитесь.\n"
            "📍 Chesterfield\n⏰ 19:30\nАкционный билет 300 рублей",
        )
        with patch("telegram_events.requests.get", return_value=Response(page)):
            events = fetch_channel_events("quizplusmsk", date(2026, 11, 3))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Квиз Плюс — КЧАУ")
        self.assertEqual(events[0]["time"], "19:30")
        self.assertEqual(events[0]["price"], "1000 руб./чел.")
        self.assertEqual(events[0]["event_url"], "https://t.me/quizplusmsk/5280")

    def test_skips_past_game_and_vague_reminder(self):
        page = post(
            "simple_quiz", 761, "2026-10-17T10:29:18+00:00",
            "Первая Ответная игра пройдет 26 октября в 20:00.\n"
            "Заявиться можно сегодня.\n📍 Лига Пап\nЦена игры — 800 рублей",
        ) + post(
            "simple_quiz", 763, "2026-10-23T11:31:52+00:00",
            "Уже в понедельник ждём вас на игре!",
        )
        upcoming = parse_channel_page(page, "simple_quiz", date(2026, 10, 20))
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0][1]["event_date"], "2026-10-26")
        self.assertEqual(upcoming[0][1]["price"], "800 руб./чел.")
        self.assertEqual(parse_channel_page(page, "simple_quiz", date(2026, 11, 3)), [])


if __name__ == "__main__":
    unittest.main()
