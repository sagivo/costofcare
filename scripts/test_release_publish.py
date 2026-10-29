import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("release_publish.py")


def dry_run(data_dir: Path) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", str(data_dir),
         "--release-prefix", "t", "--dry-run"],
        capture_output=True, text=True,
    )
    return proc.stdout + proc.stderr


class ManifestResolutionTests(unittest.TestCase):
    def test_normalized_manifest_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "x.jsonl.gz").write_bytes(b"data")
            (d / "x.jsonl.gz.manifest.json").write_text("{}")
            out = dry_run(d)
            self.assertIn("DRY   x.jsonl.gz", out)
            self.assertIn("update x.jsonl.gz.manifest.json", out)
            self.assertIn("1 upload(s) planned", out)
            self.assertEqual(sorted(p.name for p in d.iterdir()),
                             ["x.jsonl.gz", "x.jsonl.gz.manifest.json"])

    def test_missing_manifest_errors_and_plans_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "y.jsonl.gz").write_bytes(b"data")
            out = dry_run(d)
            self.assertIn("ERROR y.jsonl.gz: no sibling manifest found", out)
            self.assertNotIn("DRY ", out)
            self.assertIn("0 upload(s) planned", out)
            self.assertEqual([p.name for p in d.iterdir()], ["y.jsonl.gz"])

    def test_summary_counts_use_resolved_manifest(self):
        digest = hashlib.sha256(b"data").hexdigest()
        published = json.dumps({"release_asset": {"asset_sha256": digest}})
        for manifest_name in ("z.jsonl.gz.manifest.json", "z.manifest.json"):
            with self.subTest(manifest=manifest_name), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp) / "normalized"
                d.mkdir()
                (d / "z.jsonl.gz").write_bytes(b"data")
                (d / manifest_name).write_text(published)
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), "--data-dir", str(d),
                     "--release-prefix", "t"],
                    capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                report = json.loads((Path(tmp) / "quality" / "release-publish-t.json").read_text())
                self.assertEqual(report["counts"]["manifests_with_verified_assets"], 1)
                self.assertEqual(report["counts"]["manifests_missing_verified_assets"], 0)


def run_publish(data_dir: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", str(data_dir), "--release-prefix", "t"],
        capture_output=True, text=True, env=env,
    )


class ReportMissingAndErrorFilesTests(unittest.TestCase):
    def test_fully_published_has_empty_lists(self):
        digest = hashlib.sha256(b"data").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "normalized"
            d.mkdir()
            (d / "a.jsonl.gz").write_bytes(b"data")
            (d / "a.jsonl.gz.manifest.json").write_text(
                json.dumps({"release_asset": {"asset_sha256": digest}}))
            proc = run_publish(d)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads((Path(tmp) / "quality" / "release-publish-t.json").read_text())
            self.assertEqual(report["missing_files"], [])
            self.assertEqual(report["error_files"], [])
            self.assertEqual(set(report["counts"]), {
                "files_total", "already_published", "uploaded_this_run", "idempotent_skips",
                "verified_this_run", "errors", "manifests_with_verified_assets",
                "manifests_missing_verified_assets"})

    def test_missing_manifest_is_reported_missing_and_errored_sorted(self):
        digest = hashlib.sha256(b"data").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "normalized"
            d.mkdir()
            (d / "ok.jsonl.gz").write_bytes(b"data")
            (d / "ok.jsonl.gz.manifest.json").write_text(
                json.dumps({"release_asset": {"asset_sha256": digest}}))
            (d / "zz.jsonl.gz").write_bytes(b"data")
            (d / "bad.jsonl.gz").write_bytes(b"data")
            (d / "bad.jsonl.gz.manifest.json").write_text("not json")
            proc = run_publish(d)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads((Path(tmp) / "quality" / "release-publish-t.json").read_text())
            self.assertEqual(report["missing_files"], ["bad.jsonl.gz", "zz.jsonl.gz"])
            self.assertEqual(
                sorted(e["file"] for e in report["error_files"]),
                ["bad.jsonl.gz", "zz.jsonl.gz"])
            errors = {e["file"]: e["error"] for e in report["error_files"]}
            self.assertEqual(errors["zz.jsonl.gz"], "no sibling manifest found")
            self.assertIn("cannot read manifest", errors["bad.jsonl.gz"])
            self.assertEqual(report["counts"]["errors"], 2)
            self.assertEqual(report["counts"]["manifests_missing_verified_assets"], 2)
            self.assertEqual(report["counts"]["manifests_with_verified_assets"], 1)

    def test_failed_publish_is_missing_and_errored(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            fake_gh = bindir / "gh"
            fake_gh.write_text("#!/bin/sh\necho simulated gh failure >&2\nexit 1\n")
            fake_gh.chmod(0o755)
            d = Path(tmp) / "normalized"
            d.mkdir()
            (d / "p.jsonl.gz").write_bytes(b"data")
            (d / "p.jsonl.gz.manifest.json").write_text("{}")
            env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
            proc = run_publish(d, env=env)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads((Path(tmp) / "quality" / "release-publish-t.json").read_text())
            self.assertEqual(report["missing_files"], ["p.jsonl.gz"])
            self.assertEqual(len(report["error_files"]), 1)
            self.assertEqual(report["error_files"][0]["file"], "p.jsonl.gz")
            self.assertIn("simulated gh failure", report["error_files"][0]["error"])
            self.assertEqual((d / "p.jsonl.gz.manifest.json").read_text(), "{}")


class IsAlreadyExistsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import release_publish
        finally:
            sys.path.pop(0)
        cls.is_already_exists = staticmethod(release_publish.is_already_exists)

    def test_gh_v2_duplicate_asset_message(self):
        self.assertTrue(self.is_already_exists(
            "asset under the same name already exists"))

    def test_generic_network_error_is_not_already_exists(self):
        self.assertFalse(self.is_already_exists(
            "error connecting to api.github.com: connection timed out"))


if __name__ == "__main__":
    unittest.main()
