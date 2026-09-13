"""Tests for Prucê's separate, progressively learned source map."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/pruce-sources/scripts/sources.py"
spec = importlib.util.spec_from_file_location("pruce_sources", SCRIPT)
sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sources)


class SourceMapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "pruce/sources.json"

    def upsert(self, area, source, access, **extra):
        return sources.run(self.path, "upsert", {
            "area": area, "source": source, "access": access, **extra,
        })

    def test_fresh_map_requires_no_profile_or_file(self):
        self.assertEqual(sources.run(self.path, "read"), {"sources": []})
        self.assertFalse(self.path.exists())

    def test_calendar_for_appointments_does_not_cover_academics_on_paper(self):
        calendar = self.upsert("appointments", "Google Calendar", "connected")
        notebook = self.upsert("academic_planning", "paper notebook", "manual")
        saved = sources.run(self.path, "read")["sources"]
        self.assertEqual(saved, [calendar, notebook])
        self.assertEqual(saved[0]["area"], "appointments")
        self.assertEqual(saved[1]["area"], "academic_planning")
        self.assertNotEqual(saved[0]["access"], saved[1]["access"])

    def test_manual_observation_does_not_become_connected_or_refresh_itself(self):
        seen = "2026-09-13 — notebook photo supplied in this chat"
        self.upsert("academic_planning", "paper notebook", "manual", last_seen=seen)
        self.assertEqual(sources.run(self.path, "read")["sources"][0], {
            "area": "academic_planning", "source": "paper notebook",
            "access": "manual", "last_seen": seen, "offer": None,
        })

    def test_connected_source_is_representable_without_claiming_a_scan(self):
        entry = self.upsert("applications", "Gmail", "connected")
        self.assertEqual(entry["access"], "connected")
        self.assertIsNone(entry["last_seen"])
        updated = sources.run(self.path, "upsert", {
            "area": "applications", "source": "gmail",
            "last_seen": "2026-09-13 — successfully searched in this chat",
        })
        self.assertIn("successfully searched", updated["last_seen"])

    def test_declined_offer_and_its_context_persist_without_duplicate_source(self):
        offer = {"decision": "declined",
                 "context": "look for university deadlines arriving by email"}
        self.upsert("academic_planning", "Gmail", "unavailable", offer=offer)
        sources.run(self.path, "upsert", {
            "area": " ACADEMIC_PLANNING ", "source": " gmail ",
            "last_seen": "2026-09-13 — owner said not now",
        })
        saved = sources.run(self.path, "read")["sources"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["offer"], offer)

    def test_map_grows_one_source_at_a_time(self):
        first = self.upsert("notes", "Obsidian", "unavailable")
        self.assertEqual(sources.run(self.path, "read")["sources"], [first])
        second = self.upsert("personal_tasks", "mostly in my head", "manual")
        self.assertEqual(sources.run(self.path, "read")["sources"], [first, second])

    def test_invalid_or_corrupt_map_is_never_reset(self):
        self.upsert("documents", "local files", "manual")
        for raw in ("{broken", '{"sources":[] ,"sources":[]}',
                    '{"sources":[{"area":"x","source":"y","access":"always",'
                    '"last_seen":null,"offer":null}]}'):
            self.path.write_text(raw)
            with self.assertRaises(ValueError):
                sources.run(self.path, "upsert", {
                    "area": "notes", "source": "paper", "access": "manual",
                })
            self.assertEqual(self.path.read_text(), raw)

    def test_cli_treats_owner_text_as_data_and_keeps_file_private(self):
        area = "notes $(touch /tmp/not-executed) `id`"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "upsert", "--state", str(self.path)],
            input=json.dumps({"area": area, "source": "paper", "access": "manual"}),
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sources.run(self.path, "read")["sources"][0]["area"], area)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_failed_publish_preserves_previous_map(self):
        self.upsert("notes", "paper", "manual")
        before = self.path.read_bytes()
        with patch.object(sources.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                self.upsert("documents", "local files", "manual")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob(".sources-*")), [])


if __name__ == "__main__":
    unittest.main()
