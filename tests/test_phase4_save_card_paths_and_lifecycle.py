"""Tests for OoT file-select party save cards, stale port path guardrails, and Tk after cleanup."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oot_rando import pc_port
from oot_rando.gui.party_save_card import summarize_party_save
from oot_rando.gui.randomizer_gui import Application


class Phase4SaveCardPathsAndLifecycleTests(unittest.TestCase):
    def test_summarize_party_save_extracts_hearts_skulls_stones_medallions_and_songs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            seed_dir = base / "seed"
            seed_dir.mkdir()
            saves_dir = base / "saves"
            slot_dir = saves_dir / "slot_00"
            slot_dir.mkdir(parents=True)
            sav = slot_dir / "progress.sav"
            sav.write_bytes(b"fake")

            checks_data = {
                "tracker": {
                    "inventory": [
                        {"hash": "101", "item": "Kokiri Sword", "count": 1},
                        {"hash": "102", "item": "Bow", "count": 2},
                        {"hash": "103", "item": "Kokiri Emerald", "count": 1},
                        {"hash": "104", "item": "Light Medallion", "count": 1},
                        {"hash": "105", "item": "Zeldas Lullaby", "count": 1},
                        {"hash": "106", "item": "Minuet of Forest", "count": 1},
                    ],
                    "checks": {
                        "c1": {"item": "Heart Container", "collection": {"type": "bool", "hash": "201"}},
                        "c2": {"item": "Gold Skulltula Token", "collection": {"type": "bool", "hash": "202"}},
                        "c3": {"item": "Piece of Heart", "collection": {"type": "bool", "hash": "203"}},
                    },
                }
            }
            (seed_dir / "checks.json").write_text(json.dumps(checks_data), encoding="utf-8")
            fake_snap = {
                "bool": {101: True, 102: True, 103: True, 104: True, 105: True, 106: True, 201: True, 202: True, 203: False},
                "bool64": {},
                "bool64_complete": True,
            }

            with mock.patch("oot_rando.gui.party_save_card.load_snapshot", return_value=fake_snap):
                summary = summarize_party_save(seed_dir, saves_dir)

            self.assertTrue(summary["started"])
            self.assertEqual(summary["slot"], "slot_00")
            self.assertEqual(summary["hearts"], 4)
            self.assertEqual(summary["skulltulas"], 1)
            self.assertEqual(summary["done"], 2)
            self.assertEqual(summary["total"], 3)
            self.assertTrue(any(s["item"] == "Kokiri Emerald" and s["owned"] for s in summary["stones"]))
            self.assertTrue(any(m["item"] == "Light Medallion" and m["owned"] for m in summary["medallions"]))
            self.assertTrue(any(s["item"] == "Zeldas Lullaby" and s["owned"] for s in summary["songs_top"]))
            self.assertTrue(any(s["item"] == "Minuet of Forest" and s["owned"] for s in summary["songs_warp"]))

    def test_resolve_stale_port_subpath_and_nup(self):
        with tempfile.TemporaryDirectory() as td:
            ls_root = Path(td) / "Longshot"
            old_mods = ls_root / "stable" / "v3.1.1" / "mods"
            new_port = ls_root / "stable" / "v3.2.0"
            new_mods = new_port / "mods"
            new_mods.mkdir(parents=True)
            new_save = new_port / "user" / "save" / "slot_00" / "progress.sav"
            new_save.parent.mkdir(parents=True)
            new_save.write_bytes(b"sav")
            new_nup = ls_root / "oot.nup"
            new_nup.write_bytes(b"nup")

            old_save = ls_root / "stable" / "v3.1.1" / "user" / "save" / "slot_00" / "progress.sav"
            self.assertEqual(pc_port.resolve_stale_port_subpath(old_save, old_mods, new_mods), new_save)
            self.assertEqual(
                pc_port.resolve_stale_nup_path(ls_root / "stable" / "v3.1.1" / "oot.nup", new_mods, longshot_root=ls_root),
                new_nup,
            )

    def test_schedule_after_tracks_and_cancels_all_timers(self):
        app = Application.__new__(Application)
        app.closed = False
        app._after_ids = set()
        cancelled = []
        scheduled = []

        class _FakeRoot:
            def after(self, ms, cb):
                aid = "aid-" + str(len(scheduled) + 1)
                scheduled.append((aid, ms, cb))
                return aid

            def after_cancel(self, aid):
                cancelled.append(aid)

        app.root = _FakeRoot()
        fired = []
        aid1 = app._schedule_after(100, lambda: fired.append("one"))
        aid2 = app._schedule_after(200, lambda: fired.append("two"))
        self.assertEqual(app._after_ids, {aid1, aid2})
        app.closed = True
        app._cancel_all_after()
        self.assertEqual(set(cancelled), {aid1, aid2})
        self.assertEqual(app._after_ids, set())
        scheduled[0][2]()
        self.assertEqual(fired, [])


if __name__ == "__main__":
    unittest.main()
