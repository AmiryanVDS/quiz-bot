import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_events


class UpdateEventsTests(unittest.TestCase):
    def test_future_channel_game_survives_when_announcement_leaves_recent_pages(self):
        game = {
            "name": "Квиз Плюс — КЧАУ", "org": "Квиз Плюс",
            "event_date": "2099-11-09", "time": "19:30",
            "location": "Chesterfield | Новый Арбат, 19",
            "source_channel": "quizplusmsk",
            "event_url": "https://t.me/quizplusmsk/5280",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "events.json"
            output.write_text(json.dumps({"events": [game]}), encoding="utf-8")
            with patch.object(update_events, "OUTPUT_FILE", output), \
                 patch.object(update_events, "fetch_events", return_value=[]), \
                 patch.object(update_events, "fetch_channel_events", return_value=[]):
                update_events.main()
            result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["events"], [game])


if __name__ == "__main__":
    unittest.main()
