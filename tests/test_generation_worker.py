"""Spawned generation must keep progress, results and failures off the Tk thread."""
import _src_path  # noqa: F401
import os
import threading
import time
import unittest

from oot_rando.gui.generation_worker import run_in_process


def blocking_task(progress):
    progress('started')
    if os.name == 'nt':
        import ctypes
        # Deliberately retain the GIL, like a blocking native extension can.
        ctypes.PyDLL('kernel32').Sleep(400)
    else:
        time.sleep(0.4)
    progress('finished')
    return os.getpid()


def failing_task(progress):
    progress('before error')
    raise ValueError('invalid game fixture')


def crashed_task(progress):
    os._exit(7)


class GenerationWorkerTests(unittest.TestCase):
    def test_tk_heartbeat_survives_native_work_and_receives_progress(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'Tk display unavailable: {error}')
        root.withdraw()
        messages, results, errors, beats = [], [], [], []

        def work():
            try:
                results.append(run_in_process(blocking_task, (), messages.append))
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=work)
        worker.start()
        deadline = time.monotonic() + 15

        def heartbeat():
            beats.append(time.monotonic())
            if worker.is_alive() and time.monotonic() < deadline:
                root.after(10, heartbeat)
            else:
                root.quit()
        try:
            root.after(0, heartbeat)
            root.mainloop()
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(messages, ['started', 'finished'])
            self.assertNotEqual(results[0], os.getpid())
            self.assertGreater(len(beats), 10)
            self.assertLess(max(b - a for a, b in zip(beats, beats[1:])), 0.3)
        finally:
            root.destroy()

    def test_worker_error_reaches_the_job(self):
        messages = []
        with self.assertRaisesRegex(RuntimeError, 'invalid game fixture'):
            run_in_process(failing_task, (), messages.append)
        self.assertEqual(messages, ['before error'])

    def test_worker_error_keeps_its_traceback(self):
        with self.assertRaises(RuntimeError) as caught:
            run_in_process(failing_task, (), lambda _: None)
        self.assertIn('failing_task', caught.exception.trace)
        self.assertIn('Traceback', caught.exception.trace)

    def test_worker_crash_does_not_leave_the_job_waiting(self):
        with self.assertRaisesRegex(RuntimeError, 'exit 7'):
            run_in_process(crashed_task, (), lambda _: None)


if __name__ == '__main__':
    unittest.main()
