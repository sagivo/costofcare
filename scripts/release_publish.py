#!/usr/bin/env python3
"""Publish .jsonl.gz data files as immutable, content-addressed GitHub release assets.

Each file is uploaded as "<stem>__<first16hex>.jsonl.gz" to the release
"<release-prefix>-<first2hex>". Assets are never overwritten (no --clobber). A
sibling manifest is updated with a release_asset pointer only after the asset
has been re-downloaded and its sha256 verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RELEASE_NOTES = (
    "Content-addressed CostOfCare data assets; "
    "integrity via data/quality/release-publish-* reports"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def output_of(proc: subprocess.CompletedProcess) -> str:
    return ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()


def is_already_exists(text: str) -> bool:
    lowered = text.lower()
    return "already_exists" in lowered or "already exists" in lowered or "422" in lowered


def read_manifest(path: Path) -> dict | None:
    """Return the manifest dict, None if absent. Raises ValueError if unusable."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"manifest {path.name} is not a JSON object")
    return data


def find_manifest(data_dir: Path, asset_path: Path) -> Path | None:
    """Prefer <stem>.jsonl.gz.manifest.json, else <stem>.manifest.json; None if neither exists."""
    stem = asset_path.name[: -len(".jsonl.gz")]
    for candidate in (data_dir / f"{stem}.jsonl.gz.manifest.json",
                      data_dir / f"{stem}.manifest.json"):
        if candidate.exists():
            return candidate
    return None


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def published_sha(manifest: dict | None) -> str | None:
    if not manifest:
        return None
    asset = manifest.get("release_asset")
    if isinstance(asset, dict):
        value = asset.get("asset_sha256")
        return value if isinstance(value, str) else None
    return None


def ensure_release(tag: str, repo: str) -> str | None:
    """Return None on success, otherwise an error message."""
    if run_gh(["release", "view", tag, "--repo", repo]).returncode == 0:
        return None
    created = run_gh([
        "release", "create", tag, "--repo", repo,
        "--title", tag, "--notes", RELEASE_NOTES, "--latest=false",
    ])
    if created.returncode == 0:
        return None
    # Another run may have created it in the meantime.
    if run_gh(["release", "view", tag, "--repo", repo]).returncode == 0:
        return None
    return f"release create failed: {output_of(created)}"


def lookup_download_url(tag: str, repo: str, asset_name: str) -> str | None:
    proc = run_gh(["release", "view", tag, "--repo", repo, "--json", "assets"])
    if proc.returncode != 0:
        return None
    try:
        assets = json.loads(proc.stdout).get("assets", [])
    except json.JSONDecodeError:
        return None
    for asset in assets:
        if asset.get("name") == asset_name:
            return asset.get("url") or asset.get("browser_download_url")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, help="e.g. data/normalized")
    parser.add_argument("--release-prefix", required=True, help="e.g. data-norm")
    parser.add_argument("--repo", default="sagivo/costofcare")
    parser.add_argument("--limit", type=int, default=250, help="max uploads this run")
    parser.add_argument("--dry-run", action="store_true",
                        help="print intended actions; no gh, uploads, or writes")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        if not args.dry_run:
            print(f"error: data dir not found: {data_dir}", file=sys.stderr)
            return 2
        print(f"warning: data dir not found: {data_dir} (dry-run: treating as empty)")
        files: list[Path] = []
    else:
        files = sorted(data_dir.glob("*.jsonl.gz"), key=lambda p: p.name)

    counts = {
        "files_total": len(files),
        "already_published": 0,
        "uploaded_this_run": 0,
        "idempotent_skips": 0,
        "verified_this_run": 0,
        "errors": 0,
        "manifests_with_verified_assets": 0,
        "manifests_missing_verified_assets": 0,
    }
    hard_error = False
    file_hashes: dict[Path, str] = {}
    error_files: list[dict[str, str]] = []

    for path in files:
        stem = path.name[: -len(".jsonl.gz")]
        manifest_path = find_manifest(data_dir, path)
        if manifest_path is None:
            counts["errors"] += 1
            error_files.append({"file": path.name, "error": "no sibling manifest found"})
            print(f"ERROR {path.name}: no sibling manifest found")
            continue

        try:
            manifest = read_manifest(manifest_path)
        except ValueError as exc:
            counts["errors"] += 1
            error_files.append({"file": path.name, "error": f"{exc}"})
            print(f"ERROR {path.name}: {exc}")
            continue
        if manifest is None:
            counts["errors"] += 1
            error_files.append({"file": path.name, "error": "no sibling manifest found"})
            print(f"ERROR {path.name}: no sibling manifest found")
            continue

        try:
            digest = sha256_file(path)
        except OSError as exc:
            counts["errors"] += 1
            error_files.append({"file": path.name, "error": f"cannot read file: {exc}"})
            print(f"ERROR {path.name}: cannot read file: {exc}")
            continue
        file_hashes[path] = digest

        if published_sha(manifest) == digest:
            counts["already_published"] += 1
            print(f"SKIP  {path.name}: already published (sha256 {digest[:16]})")
            continue

        asset_name = f"{stem}__{digest[:16]}.jsonl.gz"
        tag = f"{args.release_prefix}-{digest[:2]}"

        if counts["uploaded_this_run"] >= args.limit:
            print(f"DEFER {path.name}: upload limit {args.limit} reached")
            continue

        if args.dry_run:
            counts["uploaded_this_run"] += 1
            print(f"DRY   {path.name}: would ensure release {tag}, upload as {asset_name}, "
                  f"verify, update {manifest_path.name}")
            continue

        err = ensure_release(tag, args.repo)
        if err:
            counts["errors"] += 1
            error_files.append({"file": path.name, "error": f"{err}"})
            print(f"ERROR {path.name}: {err}")
            continue

        with tempfile.TemporaryDirectory(prefix="release_publish_upload_") as stage_dir:
            staged = Path(stage_dir) / asset_name
            try:
                try:
                    os.link(path, staged)
                except OSError:
                    shutil.copyfile(path, staged)
            except OSError as exc:
                counts["errors"] += 1
                error_files.append({"file": path.name, "error": f"cannot stage upload file: {exc}"})
                print(f"ERROR {path.name}: cannot stage upload file: {exc}")
                continue
            upload = run_gh([
                "release", "upload", tag, str(staged), "--repo", args.repo,
            ])
        uploaded = False
        if upload.returncode == 0:
            uploaded = True
        elif is_already_exists(output_of(upload)):
            counts["idempotent_skips"] += 1
        else:
            counts["errors"] += 1
            error_files.append({"file": path.name, "error": f"upload failed: {output_of(upload)}"})
            print(f"ERROR {path.name}: upload failed: {output_of(upload)}")
            continue

        with tempfile.TemporaryDirectory(prefix="release_publish_") as tmpdir:
            download = run_gh([
                "release", "download", tag, "--repo", args.repo,
                "--pattern", asset_name, "--dir", tmpdir, "--skip-existing",
            ])
            downloaded = Path(tmpdir) / asset_name
            if download.returncode != 0 or not downloaded.is_file():
                counts["errors"] += 1
                error_files.append({"file": path.name, "error": f"verification download failed: {output_of(download)}"})
                print(f"ERROR {path.name}: verification download failed: {output_of(download)}")
                continue
            downloaded_sha = sha256_file(downloaded)

        if uploaded:
            counts["uploaded_this_run"] += 1

        if downloaded_sha != digest:
            counts["errors"] += 1
            hard_error = True
            error_files.append({"file": path.name, "error": f"hash mismatch for {tag}/{asset_name}: "
                  f"expected {digest}, downloaded {downloaded_sha}; manifest NOT updated"})
            print(f"FATAL {path.name}: hash mismatch for {tag}/{asset_name}: "
                  f"expected {digest}, downloaded {downloaded_sha}; manifest NOT updated")
            continue
        counts["verified_this_run"] += 1

        download_url = lookup_download_url(tag, args.repo, asset_name)
        if not download_url:
            counts["errors"] += 1
            error_files.append({"file": path.name, "error": f"verified, but no download_url found for {asset_name}; manifest NOT updated"})
            print(f"ERROR {path.name}: verified, but no download_url found for {asset_name}; "
                  "manifest NOT updated")
            continue

        updated = dict(manifest)
        updated["release_asset"] = {
            "release": tag,
            "asset_name": asset_name,
            "download_url": download_url,
            "asset_sha256": digest,
            "published_at": utc_now(),
        }
        try:
            write_json_atomic(manifest_path, updated)
        except OSError as exc:
            counts["errors"] += 1
            error_files.append({"file": path.name, "error": f"cannot write manifest: {exc}"})
            print(f"ERROR {path.name}: cannot write manifest: {exc}")
            continue
        action = "uploaded" if uploaded else "already on release"
        print(f"OK    {path.name}: {action}, verified, manifest updated -> {tag}/{asset_name}")

    if args.dry_run:
        print(f"dry-run: {counts['uploaded_this_run']} upload(s) planned of "
              f"{counts['files_total']} file(s); {counts['already_published']} already published; "
              "no changes made")
        return 0

    missing_files: set[str] = set()
    for path, digest in file_hashes.items():
        manifest_path = find_manifest(data_dir, path)
        try:
            ok = manifest_path is not None and published_sha(read_manifest(manifest_path)) == digest
        except ValueError:
            ok = False
        counts["manifests_with_verified_assets" if ok else "manifests_missing_verified_assets"] += 1
        if not ok:
            missing_files.add(path.name)
    counts["manifests_missing_verified_assets"] += counts["files_total"] - len(file_hashes)
    missing_files.update(p.name for p in files if p not in file_hashes)

    report_path = data_dir.parent / "quality" / f"release-publish-{args.release_prefix}.json"
    write_json_atomic(report_path, {
        "generated_at": utc_now(),
        "data_dir": str(args.data_dir),
        "release_prefix": args.release_prefix,
        "counts": counts,
        "missing_files": sorted(missing_files),
        "error_files": error_files,
    })
    print(f"report: {report_path}")
    print(json.dumps(counts))
    return 1 if hard_error else 0


if __name__ == "__main__":
    sys.exit(main())
