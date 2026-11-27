# Regression tests for Longshot multi-channel upgrades, party migration, and party health/preflight.
import _src_path  # noqa: F401
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oot_rando import pc_port
from oot_rando.parties import PartyLibrary
from oot_rando.party_health import check_party_health, preflight_mods_operation
from oot_rando.patching.randomize_kokiri import BUILD, TITLE
from oot_rando.randomizer.randomizer_core import ADAPTER_VERSION, GENERATOR_VERSION, Settings, settings_identity

def _make_port(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "image.bin").write_bytes(b"img")
    (root / "romfs" / "Pack").mkdir(parents=True, exist_ok=True)
    (root / "romfs" / "Pack" / "ZsDic.pack.zs").write_bytes(b"zsdic")
    (root / "mods").mkdir(parents=True, exist_ok=True)
    return root


def _make_fake_seed(seed_dir: Path, seed_label: str = "testseed") -> str:
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
    (seed_dir / "checks.json").write_text(
        json.dumps({"seed_id": seed_id, "checks": []}), encoding="utf-8"
    )
    return seed_id


class LongshotChannelAndMigrationTests(unittest.TestCase):
    def test_single_channel_upgrade_from_deleted_v3_1_1_to_v3_2_0(self):
        with tempfile.TemporaryDirectory() as td:
            ls_root = Path(td) / "Longshot"
            v320 = _make_port(ls_root / "stable" / "v3.2.0")
            stale_mods = ls_root / "stable" / "v3.1.1" / "mods"

            info = pc_port.resolve_longshot_update(stale_mods)
            self.assertEqual(info["status"], "upgraded")
            self.assertEqual(info["current_channel"], "stable")
            self.assertEqual(info["recommended"]["port_dir"], v320)
            self.assertEqual(info["recommended"]["mods_dir"], v320 / "mods")

            same = pc_port.resolve_longshot_update(v320 / "mods")
            self.assertEqual(same["status"], "unchanged")

    def test_multi_channel_always_prompts_with_all_three_channels(self):
        with tempfile.TemporaryDirectory() as td:
            ls_root = Path(td) / "Longshot"
            _make_port(ls_root / "stable" / "v3.2.0")
            _make_port(ls_root / "release candidate" / "v3.2.1-rc.2")
            _make_port(ls_root / "release candidate" / "v3.2.1-rc.1")
            _make_port(ls_root / "nightly" / "2026-11-24")
            _make_port(ls_root / "nightly" / "2026-11-20")

            info = pc_port.resolve_longshot_update(ls_root / "stable" / "v3.1.1" / "mods")
            self.assertEqual(info["status"], "choose_channel")
            names = [(c["channel"], c["version_name"]) for c in info["channels"]]
            self.assertEqual(
                names,
                [
                    ("stable", "v3.2.0"),
                    ("release candidate", "v3.2.1-rc.2"),
                    ("nightly", "2026-11-24"),
                ],
            )
            self.assertEqual(info["recommended"]["channel"], "stable")

    def test_normalize_port_mods_dir_resolves_port_root(self):
        with tempfile.TemporaryDirectory() as td:
            v320 = _make_port(Path(td) / "Longshot" / "stable" / "v3.2.0")
            self.assertEqual(pc_port.normalize_port_mods_dir(str(v320) + os.sep), str(v320 / "mods"))
            self.assertEqual(pc_port.normalize_port_mods_dir(str(v320 / "mods") + os.sep), str(v320 / "mods"))

    def test_party_library_migrates_stale_parties_and_activates_when_outgoing_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            ls_root = base / "Longshot"
            v311 = _make_port(ls_root / "stable" / "v3.1.1")
            v320 = _make_port(ls_root / "stable" / "v3.2.0")
            saves = base / "saves" / "account01"
            saves.mkdir(parents=True)

            lib = PartyLibrary(base / "Parties")
            seed1 = base / "tmp_seed1"
            _make_fake_seed(seed1, "oldpartyseed")
            with mock.patch.object(lib, "_closed"):
                p1 = lib.create("OldParty", seed1, v311 / "mods", saves)
                lib.activate(p1["id"])
            (saves / "slot_00").mkdir(parents=True)
            (saves / "slot_00" / "progress.sav").write_bytes(b"sav")

            # Simulate Longshot deleting v3.1.1 on update to v3.2.0
            import shutil
            shutil.rmtree(v311)

            # Activating a new party on v3.2.0 must succeed even when outgoing v3.1.1/mods is gone
            seed2 = base / "tmp_seed2"
            _make_fake_seed(seed2, "newpartyseed")
            p2 = lib.create("NewParty", seed2, v320 / "mods", saves)
            with mock.patch.object(lib, "_closed"):
                lib.activate(p2["id"])
            self.assertEqual(lib.active_id, p2["id"])

            # Migrating remaining stale v3.1.1 parties updates OldParty to v3.2.0/mods
            migrated = lib.migrate_mods_directory(v320 / "mods", old_mods=v311 / "mods", root=ls_root)
            self.assertEqual(migrated, ["OldParty"])
            p1_after = lib.get(p1["id"])
            self.assertEqual(Path(p1_after["mods"]), (v320 / "mods").resolve())



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




class PartyHealthAndPreflightTests(unittest.TestCase):
    def test_health_and_preflight_checks(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            mods = base / "mods"
            mods.mkdir()
            saves = base / "saves"
            saves.mkdir()

            lib = _FakePartyLibrary(base / "Parties")
            pa = lib.add_party("3" * 32, "Party C", "seed_gamma", mods, saves)
            lib.activate(pa["id"])

            health = check_party_health(lib, pa["id"])
            self.assertTrue(health["ok"])
            codes = {c["code"] for c in health["checks"]}
            self.assertIn("manifest", codes)
            self.assertIn("live_seed", codes)

            pf_ok = preflight_mods_operation(mods, required_bytes=1024, min_error_bytes=512)
            self.assertTrue(pf_ok["ok"])

            pf_missing = preflight_mods_operation(mods, source_paths=[base / "missing.zip"])
            self.assertFalse(pf_missing["ok"])
            self.assertTrue(any("Missing source" in e for e in pf_missing["errors"]))


if __name__ == "__main__":
    unittest.main()
