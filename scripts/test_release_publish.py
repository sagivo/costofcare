import hashlib
import json
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
