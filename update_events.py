# -*- coding: utf-8 -*-

import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup


SPORT_URL = "https://findquiz.ru/category/sport"
OUTPUT_FILE = Path(__file__).with_name("events.json")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def request_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }


def fetch_events() -> list[dict]:
    response = requests.get(
        SPORT_URL,
        headers=request_headers(),
        timeout=30,
        verify=False,
    )
    response.raise_for_status()
    response.encoding = "utf-8"

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.find_all("li", class_="top")
    events = []

    for item in items:
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
                day_digits = "".join(char for char in raw_day if char.isdigit())
                day = day_digits or "?"
                weekday = "".join(
                    char for char in raw_day if char.isalpha()
                ).upper()

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
        raise RuntimeError("FindQuiz returned no sports events")

    return events


def main() -> None:
    events = fetch_events()
    payload = {
        "ok": True,
        "source": SPORT_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(events),
        "events": events,
    }
    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(events)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
