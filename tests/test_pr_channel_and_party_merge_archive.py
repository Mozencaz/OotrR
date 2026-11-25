"""Tests for Longshot pull request channel, per-party Merged_Zelda_Rando archive, and party health/preflight."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from oot_rando import pc_port
from oot_rando.gui.parties_page import PartiesPage
from oot_rando.patching.randomize_kokiri import BUILD, TITLE
from oot_rando.party_health import check_party_health, preflight_mods_operation
from oot_rando.randomizer.randomizer_core import ADAPTER_VERSION, GENERATOR_VERSION, Settings, settings_identity
from oot_rando.randomizer.randomizer_services import read_artifact


def _make_port(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "image.bin").write_bytes(b"img")
    (root / "romfs").mkdir(parents=True, exist_ok=True)
    (root / "mods").mkdir(parents=True, exist_ok=True)
    return root


def _make_fake_seed(seed_dir: Path, seed_label: str) -> str:
    settings = Settings(seed=seed_label)
    seed_id = settings_identity(settings)
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "romfs").mkdir(exist_ok=True)
    data = seed_label.encode("utf-8")
    (seed_dir / "romfs" / "resource").write_bytes(data)
    manifest = {
        "schema_version": 1,
        "title_id": TITLE,
        "build_id": BUILD,
        "seed_id": seed_id,
        "generator_version": GENERATOR_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "settings": settings.to_dict(),
        "files": {
            "resource": {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        },
    }
    (seed_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (seed_dir / "checks.json").write_text(json.dumps({"seed_id": seed_id, "checks": []}), encoding="utf-8")
    return seed_id


class _FakePartyLibrary:
    def __init__(self, root: Path):
        self.root = root
        self.active_id = None
        self._parties = {}

    def _closed(self):
        return None

    def folder(self, ident: str) -> Path:
        return self.root / ident

    def get(self, ident: str) -> dict:
        return dict(self._parties[ident])

    def bundle(self, party: dict) -> Path:
        return self.folder(party["id"]) / "snapshots" / party["revision"]

    def add_party(self, ident: str, name: str, seed_label: str, mods: Path, saves: Path) -> dict:
        rev = "a" * 32
        pdir = self.folder(ident)
        seed_dst = pdir / "snapshots" / rev / "seed"
        seed_id = _make_fake_seed(seed_dst, seed_label)
        party = {
            "id": ident,
            "name": name,
            "revision": rev,
            "seed_id": seed_id,
            "mod_name": "OoT_Rando_" + seed_label,
            "mods": str(mods),
            "saves": str(saves),
        }
        (pdir / "party.json").write_text(json.dumps(party), encoding="utf-8")
        self._parties[ident] = party
        return dict(party)

    def activate(self, ident: str) -> dict:
        if self.active_id:
            prev = self._parties[self.active_id]
            prev_live = Path(prev["mods"]) / prev["mod_name"]
            if not prev_live.is_dir():
                raise RuntimeError("Outgoing raw seed missing during activate")
            shutil.rmtree(prev_live)
        target = self._parties[ident]
        dst = Path(target["mods"]) / target["mod_name"]
        shutil.copytree(self.bundle(target) / "seed", dst)
        self.active_id = ident
        return dict(target)


class _DummyPartiesHost(PartiesPage):
    def __init__(self, library, stage_root: Path):
        self.party_library = library
        self._midna_host = None
        self._last_midna_switch_note = ""
        self._stage = stage_root

    def _midna_stage_root(self) -> Path:
        return self._stage


class LongshotPullRequestChannelTests(unittest.TestCase):
    def test_pull_request_aliases_and_four_channel_ranking(self):
        for raw in ("pull request", "Pull Requests", "pull-request", "pull_requests", "pr", "PRs"):
            self.assertEqual(pc_port.canonical_channel_name(raw), "pull request")
        self.assertEqual(pc_port.channel_display_name("pull request"), "Pull Request")
        self.assertEqual(pc_port.canonical_channel_name("release candidate"), "release candidate")

        with tempfile.TemporaryDirectory() as td:
            ls_root = Path(td) / "Longshot"
            _make_port(ls_root / "stable" / "v3.2.0")
            _make_port(ls_root / "release candidate" / "v3.2.1-rc.1")
            _make_port(ls_root / "nightly" / "2026-11-24")
            _make_port(ls_root / "pull request" / "pr-99")
            _make_port(ls_root / "pull request" / "pr-100")

            info = pc_port.resolve_longshot_update(ls_root / "stable" / "v3.1.1" / "mods")
            self.assertEqual(info["status"], "choose_channel")
            self.assertEqual(
                [(c["channel"], c["version_name"]) for c in info["channels"]],
                [
                    ("stable", "v3.2.0"),
                    ("release candidate", "v3.2.1-rc.1"),
                    ("nightly", "2026-11-24"),
                    ("pull request", "pr-100"),
                ],
            )

    def test_single_pull_request_channel_upgrade(self):
        with tempfile.TemporaryDirectory() as td:
            ls_root = Path(td) / "Longshot"
            pr205 = _make_port(ls_root / "Pull Requests" / "PR #205")
            stale = ls_root / "Pull Requests" / "PR #201" / "mods"
            info = pc_port.resolve_longshot_update(stale)
            self.assertEqual(info["status"], "upgraded")
            self.assertEqual(info["current_channel"], "pull request")
            self.assertEqual(info["recommended"]["port_dir"], pr205)


class PartyMergedModArchiveTests(unittest.TestCase):
    def test_archive_and_auto_restore_merged_mod_across_party_switches(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            mods = base / "mods"
            mods.mkdir()
            saves = base / "saves" / "account01"
            saves.mkdir(parents=True)

            lib = _FakePartyLibrary(base / "Parties")
            host = _DummyPartiesHost(lib, base / "staged")

            pa = lib.add_party("1" * 32, "Party A", "seed_alpha", mods, saves)
            pb = lib.add_party("2" * 32, "Party B", "seed_beta", mods, saves)
            lib.activate(pa["id"])

            # Simulate Midna having merged Party A (raw seed removed, Merged_Zelda_Rando active)
            shutil.rmtree(mods / pa["mod_name"])
            merged_a = mods / "Merged_Zelda_Rando"
            (merged_a / "romfs").mkdir(parents=True)
            (merged_a / "romfs" / "marker.txt").write_text("merged_for_A", encoding="utf-8")

            # Switch A -> B: A merged mod archived alongside Party A, B raw seed installed
            manifest_b, _ = read_artifact(lib.bundle(pb) / "seed")
            host._run_with_midna_bridge(mods, manifest_b, lambda: lib.activate(pb["id"]))
            self.assertFalse((mods / "Merged_Zelda_Rando").exists())
            self.assertTrue((mods / pb["mod_name"]).is_dir())
            archived_a = lib.folder(pa["id"]) / "midna_merged" / "Merged_Zelda_Rando" / "romfs" / "marker.txt"
            self.assertEqual(archived_a.read_text(encoding="utf-8"), "merged_for_A")

            # Switch B -> A: A merged mod auto-restored and duplicate raw seed removed
            manifest_a, _ = read_artifact(lib.bundle(pa) / "seed")
            host._run_with_midna_bridge(mods, manifest_a, lambda: lib.activate(pa["id"]))
            restored_marker = mods / "Merged_Zelda_Rando" / "romfs" / "marker.txt"
            self.assertEqual(restored_marker.read_text(encoding="utf-8"), "merged_for_A")
            self.assertFalse((mods / pa["mod_name"]).exists())
            self.assertIn("restored Merged_Zelda_Rando", host._last_midna_switch_note)

    def test_mismatched_seed_id_archive_is_not_restored(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            mods = base / "mods"
            mods.mkdir()
            saves = base / "saves" / "account01"
            saves.mkdir(parents=True)

            lib = _FakePartyLibrary(base / "Parties")
            host = _DummyPartiesHost(lib, base / "staged")
            pa = lib.add_party("1" * 32, "Party A", "seed_alpha", mods, saves)
            lib.activate(pa["id"])

            bad_arch = lib.folder(pa["id"]) / "midna_merged"
            (bad_arch / "Merged_Zelda_Rando").mkdir(parents=True)
            (bad_arch / "meta.json").write_text(json.dumps({"seed_id": "wrong-seed"}), encoding="utf-8")

            self.assertFalse(host._restore_party_merged_mod(pa))
            self.assertFalse((mods / "Merged_Zelda_Rando").exists())
            self.assertTrue((mods / pa["mod_name"]).is_dir())


class PartyHealthAndPreflightTests(unittest.TestCase):
    def test_health_and_preflight_checks(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            mods = base / "mods"
            mods.mkdir()
            saves = base / "saves"
            saves.mkdir()
            stage = base / "staged"
            (stage / "ConflictingUI").mkdir(parents=True)

            lib = _FakePartyLibrary(base / "Parties")
            pa = lib.add_party("3" * 32, "Party C", "seed_gamma", mods, saves)
            lib.activate(pa["id"])

            health = check_party_health(lib, pa["id"], stage_root=stage)
            self.assertTrue(health["ok"])
            codes = {c["code"] for c in health["checks"]}
            self.assertIn("manifest", codes)
            self.assertIn("live_seed", codes)
            self.assertIn("staged_leftovers", codes)

            pf_ok = preflight_mods_operation(mods, required_bytes=1024, min_error_bytes=512)
            self.assertTrue(pf_ok["ok"])

            pf_missing = preflight_mods_operation(mods, source_paths=[base / "missing.zip"])
            self.assertFalse(pf_missing["ok"])
            self.assertTrue(any("Missing source" in e for e in pf_missing["errors"]))


if __name__ == "__main__":
    unittest.main()
