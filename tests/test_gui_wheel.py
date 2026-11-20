"""Mouse wheel scrolling of the GUI's pages."""
import _src_path  # noqa: F401  (src on sys.path)
import unittest

from oot_rando.gui import theme


class WheelTests(unittest.TestCase):
    def test_x11_buttons_scroll(self):
        self.assertIn('<Button-4>', theme.WHEEL_EVENTS)
        self.assertIn('<Button-5>', theme.WHEEL_EVENTS)
        self.assertEqual(theme.wheel_units(4, 0), -1)
        self.assertEqual(theme.wheel_units(5, 0), 1)

    def test_mouse_wheel_delta(self):
        self.assertEqual(theme.wheel_units('??', 120), -1)
        self.assertEqual(theme.wheel_units('??', -240), 2)
        # Small deltas (macOS, touchpads) still move a line.
        self.assertEqual(theme.wheel_units('??', 3), -1)
        self.assertEqual(theme.wheel_units('??', -1), 1)
        self.assertEqual(theme.wheel_units('??', 0), 0)


if __name__ == '__main__':
    unittest.main()
