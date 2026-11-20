#!/usr/bin/env python3
"""Quarantine a normalized manifest whose extraction is not trustworthy.

Adds a top-level "quarantine" object and marks the scan flags incomplete; all other
fields (including release_asset) are preserved. A later verified-complete extraction
overwrites the manifest without the quarantine key, which is the recovery path.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, help="normalized file id (without .jsonl.gz)")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--evidence-file", required=True, help="JSON file with supporting evidence")
    parser.add_argument("--data-dir", default="data/normalized")
    args = parser.parse_args()

    path = Path(args.data_dir) / f"{args.id}.jsonl.gz.manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        evidence = json.loads(Path(args.evidence_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not isinstance(manifest, dict):
        print(f"error: manifest {path.name} is not a JSON object", file=sys.stderr)
        return 2

    existing = manifest.get("quarantine")
    if isinstance(existing, dict):
        quarantine = dict(existing)
    else:
        quarantine = {"prior_release_asset": copy.deepcopy(manifest.get("release_asset"))}
    quarantine["quarantined_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    quarantine["reason"] = args.reason
    quarantine["evidence"] = evidence

    manifest["quarantine"] = quarantine
    manifest["complete_source_download"] = False
    manifest["complete_target_code_scan"] = False

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    print(json.dumps({
        "id": args.id,
        "manifest": str(path),
        "quarantined_at": quarantine["quarantined_at"],
        "reason": args.reason,
        "prior_release_asset": quarantine["prior_release_asset"] is not None,
        "updated_existing": isinstance(existing, dict),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
