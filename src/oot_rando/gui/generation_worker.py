"""Keep CPU-heavy generation outside the Tk process, including in portable builds."""
import multiprocessing


class WorkerError(RuntimeError):
    """A failure inside the worker process; ``trace`` is its traceback there."""

    def __init__(self, message, trace=''):
        super().__init__(message)
        self.trace = trace


def _entry(send, function, args):
    try:
        result = function(*args, progress=lambda message: send.send(('progress', message)))
        send.send(('done', result))
    except Exception as error:
        import traceback
        send.send(('error', (str(error), traceback.format_exc())))
    finally:
        send.close()


def run_in_process(function, args, progress):
    """Run a picklable task, forwarding progress/results to the caller's job thread."""
    context = multiprocessing.get_context('spawn')
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_entry, args=(send, function, args), daemon=True)
    try:
        process.start()
        send.close()
        while True:
            try:
                kind, payload = receive.recv()
            except EOFError:
                process.join()
                raise RuntimeError(f'Generation worker stopped unexpectedly (exit {process.exitcode}).') from None
            if kind == 'progress':
                progress(payload)
            elif kind == 'done':
                process.join()
                return payload
            else:
                message, trace = payload
                raise WorkerError(message, trace)
    finally:
        send.close()
        receive.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join()
            process.close()


def _generate(nup, mods, settings, archive, progress):
    from oot_rando.randomizer.randomizer_core import Settings
    from oot_rando.randomizer.mods_folder import generate_in_mods
    return generate_in_mods(nup, mods, Settings.from_dict(settings), progress, archive=archive)


def generate_isolated(nup, mods, settings, archive, progress):
    return run_in_process(_generate, (nup, mods, settings.to_dict(), archive), progress)
