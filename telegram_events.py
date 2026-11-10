"""Read explicit game announcements from public Telegram channel pages."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


CHANNELS = {
    "simple_quiz": "Ответная игра",
    "quizplusmsk": "Квиз Плюс",
    "quizpubrangers": "Quiz Pub Rangers",
}
MOSCOW = ZoneInfo("Europe/Moscow")
MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
WEEKDAYS = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
DATE_PATTERN = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\b", re.I)
TIME_PATTERN = re.compile(
    r"начал[оаеи]\s*(?:игры)?\s*[-—–:]?\s*(?:в\s*)?(\d{1,2}:\d{2})",
    re.I,
)
PRICE_PATTERNS = (
    re.compile(r"цена\s+игры\D{0,40}(\d[\d\s]{1,5})\s*(?:руб|₽)", re.I),
    re.compile(r"стандартный\s+билет\D{0,70}(\d[\d\s]{1,5})\s*(?:руб|₽)", re.I),
)


def _event_date(text: str, published: datetime) -> date | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    day, month = int(match.group(1)), MONTHS[match.group(2).lower()]
    local_date = published.astimezone(MOSCOW).date()
    try:
        candidate = date(local_date.year, month, day)
        if candidate < local_date - timedelta(days=30):
            candidate = date(local_date.year + 1, month, day)
        return candidate
    except ValueError:
        return None


def _start_time(text: str) -> str | None:
    match = TIME_PATTERN.search(text)
    if not match:
        match = re.search(
            r"\b\d{1,2}\s+(?:" + "|".join(MONTHS) + r")\s+в\s+(\d{1,2}:\d{2})",
            text,
            re.I,
        )
    if not match:
        match = re.search(r"(?:⌚|⏰|🕖)\ufe0f?\s*(\d{1,2}:\d{2})", text)
    if not match:
        return None
    hour, minute = (int(part) for part in match.group(1).split(":"))
    return f"{hour:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def _location(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        for marker in ("📍", "🏟"):
            if marker not in line:
                continue
            value = line.split(marker, 1)[1].strip(" \ufe0f:—–-")
            if not value and index + 1 < len(lines):
                value = lines[index + 1].strip()
            if value:
                return value[:120]
    return None


def _price(text: str) -> str:
    jersey_price = re.search(
        r"\bвход\s*:\s*(\d+)\s*₽\s*без\s+джерси\s*/\s*"
        r"(\d+)\s*₽\s*в\s+клубной\s+джерси",
        text,
        re.I,
    )
    if jersey_price:
        return (
            f"{jersey_price.group(1)} руб./чел. "
            f"({jersey_price.group(2)} руб. в клубной джерси)"
        )
    for pattern in PRICE_PATTERNS:
        match = pattern.search(text)
        if match:
            amount = re.sub(r"\s+", "", match.group(1))
            return f"{amount} руб./чел."
    return "Цена не указана"


def event_key(event: dict) -> tuple[str, str, str]:
    venue = event["location"].split("|", 1)[0].split(":", 1)[0]
    return (
        event["event_date"],
        event["time"],
        re.sub(r"\W+", "", venue.casefold()),
    )


def parse_channel_page(html: str, channel: str, today: date) -> list[tuple[datetime, dict]]:
    soup = BeautifulSoup(html, "html.parser")
    messages = soup.select(f'.tgme_widget_message[data-post^="{channel}/"]')
    if not messages:
        raise ValueError(f"Telegram did not return posts for @{channel}")

    events = []
    for message in messages:
        body = message.select_one(".tgme_widget_message_text")
        timestamp = message.select_one("time[datetime]")
        if not body or not timestamp:
            continue
        lines = [line.strip() for line in body.get_text("\n", strip=True).splitlines() if line.strip()]
        text = " ".join(lines)
        if not re.search(r"квиз|игр[ауеы]|запис|заяв", text, re.I):
            continue
        published = datetime.fromisoformat(timestamp["datetime"].replace("Z", "+00:00"))
        event_date = _event_date(text, published)
        start_time = _start_time(text)
        location = _location(lines)
        if not event_date or event_date < today or not start_time or not location:
            continue

        name = CHANNELS[channel]
        if channel == "quizplusmsk":
            title = lines[0]
            theme = re.search(r"\b\d{1,2}\s+(?:" + "|".join(MONTHS) + r")!\s*(.+)$", title, re.I)
            if theme:
                name += " — " + theme.group(1).strip(" !")[:70]

        event_id = message["data-post"].split("/", 1)[1]
        events.append((published, {
            "name": name,
            "org": CHANNELS[channel],
            "event_date": event_date.isoformat(),
            "day": f"{event_date.day:02d}",
            "weekday": WEEKDAYS[event_date.weekday()],
            "month": next(label for label, number in MONTHS.items() if number == event_date.month),
            "time": start_time,
            "location": location,
            "price": _price(text),
            "event_url": f"https://t.me/{channel}/{event_id}",
            "source_channel": channel,
        }))
    return events


def fetch_channel_events(channel: str, today: date | None = None) -> list[dict]:
    if channel not in CHANNELS:
        raise ValueError(f"Unknown channel: {channel}")
    today = today or datetime.now(MOSCOW).date()
    before = None
    all_events: list[tuple[datetime, dict]] = []
    for _ in range(3):
        url = f"https://t.me/s/{channel}"
        if before is not None:
            url += f"?before={before}"
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        messages = soup.select(f'.tgme_widget_message[data-post^="{channel}/"]')
        if not messages:
            raise ValueError(f"Telegram did not return posts for @{channel}")
        all_events.extend(parse_channel_page(response.text, channel, today))
        oldest = min(int(message["data-post"].split("/", 1)[1]) for message in messages)
        if oldest == before:
            break
        before = oldest

    unique = {}
    for published, event in sorted(all_events, key=lambda pair: pair[0]):
        unique.setdefault(event_key(event), event)
    return sorted(unique.values(), key=lambda event: (event["event_date"], event["time"]))
