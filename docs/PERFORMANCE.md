# Performance investigation — 2026-11-22

## Archipelago issue #86

[Crash before the title screen with certain Archipelago patches](https://github.com/Mozencaz/OotrR/issues/86)
reports that removing remote entries lets the game boot, but prevents item delivery.
The posted crash log alone does not establish whether the exhausted resource is
heap memory or stack space. No failing patch is attached to the report.

The old implementation adds six MainUpdate nodes for every remote item, plus a
simultaneous group for every 64 records. A 300-item mailbox adds **1,805 nodes** to
the global sequence and an event-setting row for each item.

Generator **0.12.3** instead adds **seven nodes and one event-setting row** for any
nonempty mailbox. The client writes the selected record's existing `Recv` flag,
then a shared `RandoAP.Pending` signal. The native request-and-clear sequence starts
one dispatcher event, which clears the record's request and calls its existing
item entry only if its saved `Got` receipt is false. Item selection is evaluated
on delivery rather than by hundreds of simultaneous per-frame watchers.

This addresses the demonstrated scaling problem and agrees with the reporter's
workaround. **Booting the affected game build remains untested.** The report should
not be closed solely on these offline checks.

The updated client supports older per-item mailboxes. A newly generated shared
mailbox needs the updated client. Existing remote keys and receipts are unchanged;
regeneration of the same AP slot retains its save marker through the existing
installation service. Regenerate the mod from its `.aprmk` to apply the change.

## Generation and desktop responsiveness

Generation formerly ran in a Python thread in the Tk process. It now runs in a
spawned process; the existing GUI job thread forwards progress and completion
through the event queue. Ordinary generation, regeneration and generation from an
AP patch share this path. Child exceptions and abnormal exits reach the GUI error
handler. Frozen entry points call `multiprocessing.freeze_support()`.

Actor building now reports progress every 20 actors; event analysis and resource
compression have explicit log stages.

A complete 300-remote-item seed was generated through the real `Application.run_job`
and `poll` methods with a Tk event-loop heartbeat. The final generator 0.12.3 run
completed in **77.89 seconds**; 2,489 heartbeats ran, with a **33 ms maximum gap**.
Its full verifier passed:
69 maps, 389 rewards, 300 received-item records and 189 chest flags. This measures
the generation job and event loop, not rendering every page or running the game.

## Measured refactoring

Dependency analysis repeatedly decoded an entire EVFL flow for its entry points,
each entry's calls, and transition traversal. Two `setdefault` caches also eagerly
evaluated the parse expression even when their key already existed.

Analysis now reuses parsed flowcharts within each pass and populates entry-name
caches only on a miss. These caches are local to the analysis; modified charts do
not leak into later seeds. Dependencies still follow individual entries and retain
the existing cycle and unsupported-message-flow checks.

On the same full-randomizer seed and local game file:

| Measurement with cProfile enabled | Before | After |
| --- | ---: | ---: |
| Full generation | 405.55 s | 286.16 s |
| `complete_event_info` | 137.46 s | 13.39 s |
| EVFL reads | 5,775 | 1,331 |

The full profiled run is **29.4% faster**. Profiling adds substantial overhead;
these are diagnostic timings, not a promise of normal application latency.
All **663 generated game resources** have identical checksums before and after
the analysis refactor. Checks and spoilers are identical; parsed tracking metadata
is identical (its existing unordered JSON serialization can change its byte hash).

A separate **unprofiled** before/after pair on generator 0.12.3 took **160.66 s →
130.66 s**, an **18.7% reduction**. Both runs have the same seed identity and all
663 resource hashes match. The baseline restores the original `event_info` module
only inside the benchmark process; working-tree files are not reverted. These are
single-run measurements on this machine, rather than a statistical benchmark.

The remaining main hotspot is first-collection actor construction: about 113 s of
the 286 s profiled run, dominated by repeated native AI parsing and round-trip
validation. Reusing immutable AI templates is the next refactoring candidate;
per-output round-trip and actor-behavior checks should be preserved. A broad
rewrite of the GUI or randomizer core is not needed for these changes.

## Reproduce

Run from the repository root, using exported settings or a seed manifest and a
new output folder. This creates an isolated seed, without installing it into a
game's mods folder:

```powershell
python tools/benchmark_generation.py GAME.nup SETTINGS.json build/benchmark-seed
python tools/benchmark_generation.py GAME.nup SETTINGS.json build/profile-seed --profile
python -m pstats build/profile-seed.prof
```

The benchmark writes elapsed stage timings to `<output>.benchmark.json` and,
when requested, a cProfile file. Raw investigation artifacts and the 300-item
validation patch are under `build/performance-86/` (ignored by Git).

Regression coverage includes bounded MainUpdate growth, dispatch of the last of
300 records, saved-receipt duplicate prevention, dependency completeness, paused
games, dropped-event retries, partial memory-write failures, legacy delivery,
worker errors/crashes and a Tk heartbeat during GIL-blocking native work.
