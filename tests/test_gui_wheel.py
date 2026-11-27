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

    def test_wheel_never_changes_a_setting(self):
        import tkinter as tk
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        try:
            root.withdraw()
            values = ('One', 'Two', 'Three')
            combo = ttk.Combobox(root, values=values, state='readonly')
            combo.set('Two')
            number = tk.IntVar(root, 5)
            spin = ttk.Spinbox(root, from_=1, to=10, textvariable=number)
            theme.keep_values_on_wheel(root)
            for widget_class in ('TCombobox', 'TSpinbox'):
                for sequence in theme.WHEEL_EVENTS:
                    self.assertEqual(root.bind_class(widget_class, sequence), '')
            for widget in (combo, spin):
                widget.pack()
            root.update()
            for widget in (combo, spin):
                widget.event_generate('<MouseWheel>', delta=-120, x=5, y=5)
            root.update()
            self.assertEqual(combo.get(), 'Two')
            self.assertEqual(number.get(), 5)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
