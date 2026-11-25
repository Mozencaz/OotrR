"""Tests for Phase 2 Midna dance states, embedded party banner queuing, and quick folder targets."""
import unittest
from types import SimpleNamespace
from unittest import mock

from oot_rando.midnas_devotion.ui.embedded_host import EmbeddedMidnaHost
from oot_rando.midnas_devotion.ui.midna_dance import MidnaDanceWidget


class FakeDance(MidnaDanceWidget):
    def __init__(self):
        self._state = "idle"
        self._base_interval_ms = 120
        self._movie = mock.MagicMock()
        self._timer = mock.MagicMock()
        self._style = ""

    def setStyleSheet(self, css):
        self._style = css


class Phase2MidnaUiTests(unittest.TestCase):
    def test_midna_dance_states_update_style_and_speed(self):
        d = FakeDance()
        for st in ("idle", "scanning", "merging", "success", "warning"):
            d.set_state(st)
            self.assertEqual(d.state, st)
            self.assertTrue(bool(d._style))
        d.set_state("merging")
        d._movie.setSpeed.assert_called_with(135)
        d.set_state("unknown-state")
        self.assertEqual(d.state, "idle")

    def test_embedded_host_queues_and_delivers_party_banner(self):
        host = EmbeddedMidnaHost.__new__(EmbeddedMidnaHost)
        host._destroyed = False
        host._window = None
        host._pending_party_banner = None

        host.set_party_banner("Staged mods", show_remerge=True, party_name="Run 1", stage_dir="/tmp/stage")
        self.assertEqual(host._pending_party_banner, ("Staged mods", True, "Run 1", "/tmp/stage"))

        fake_win = SimpleNamespace(set_party_banner=mock.MagicMock())
        host._window = fake_win
        host.set_party_banner("Restored merge", show_remerge=False, party_name="Run 2", stage_dir="/tmp/stage")
        fake_win.set_party_banner.assert_called_once_with(
            "Restored merge",
            show_remerge=False,
            party_name="Run 2",
            stage_dir="/tmp/stage",
        )


if __name__ == "__main__":
    unittest.main()
