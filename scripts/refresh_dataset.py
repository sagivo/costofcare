#!/usr/bin/env python3
"""Refresh the CostOfCare hospital dataset from primary sources.

Reads the MRF registry (referencesource.org canonical index, cached locally),
extracts target CPT/HCPCS standard charges from each hospital's own CMS-required
machine-readable file, and writes one JSON per hospital under data/hospitals/.

Stalest-first scheduling: hospitals never parsed (or whose MRF URL changed) go
first, then oldest extraction. A --limit bounds work per run so a daily GitHub
Action can rotate through the full registry.

Usage:
  refresh_dataset.py [--limit N] [--workers N] [--max-minutes N] [--ids a,b,c]
                     [--data-dir DIR] [--registry PATH|URL]
"""
import json, os, re, sys, time, urllib.request, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mrf_extract

REGISTRY_URL = "https://referencesource.org/hospital-price-transparency-mrf-index/data.json"

ADDR_RE = re.compile(r",\s*([A-Za-z .\-']+),\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?\s*$")

def parse_city_state(addr):
    if not addr: return None, None
    first = str(addr).split("|")[0]
    m = ADDR_RE.search(first.strip())
    if not m:
        # CMS files also commonly separate street and city with a period.
        m = re.search(r"[.]\s*([A-Za-z .\-']+),\s*([A-Z]{2})\s+(\d{5})", first)
    if not m: return None, None
    city = m.group(1).strip().title()
    return city, m.group(2)

def load_registry(source):
    if source.startswith("http"):
        with urllib.request.urlopen(source, timeout=60) as r:
            d = json.loads(r.read().decode())
    else:
        with open(source) as f:
            d = json.load(f)
    recs = [r for r in d["records"] if r.get("mrf_url")]
    return recs

def process(rec, targets, out_dir, max_bytes):
    hid = rec["id"]
    out_path = os.path.join(out_dir, hid + ".json")
    result = {"id": hid, "mrf_url": rec["mrf_url"], "status": "failed",
              "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    t0 = time.time()
    try:
        # Isolate each large source in a process with a hard wall-clock cap.
        # Temp downloads are cleaned even when a slow/invalid source is killed.
        with tempfile.TemporaryDirectory() as temp:
            parsed_path = os.path.join(temp, "parsed.json")
            child = subprocess.run([sys.executable, os.path.join(HERE, "mrf_extract.py"),
                rec["mrf_url"], parsed_path, "--max-bytes", str(max_bytes)],
                capture_output=True, text=True, timeout=180,
                env=dict(os.environ, TMPDIR=temp))
            if child.returncode != 0 or not os.path.exists(parsed_path):
                raise ValueError("extractor failed: " + child.stderr[-200:])
            parsed = json.load(open(parsed_path))
            if parsed.get("status") == "failed":
                raise ValueError(parsed.get("error", "source extraction failed"))
            result.update(parsed)
        meta = result
        city, state = parse_city_state(meta.get("hospital_address"))
        loc = (meta.get("location_name") or "").split("|")[0].strip()
        result["display_name"] = loc or meta.get("hospital_name") or rec.get("location_name") or hid
        result["city"], result["state"] = city or rec.get("city"), state or rec.get("state")
        result["status"] = "ok" if result["codes"] else "no_target_codes"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"[:300]
        result["display_name"] = rec.get("location_name") or hid
    result["seconds"] = round(time.time() - t0, 1)
    result["registry_name"] = rec.get("location_name")
    result["source_page_url"] = rec.get("source_page_url")
    result["last_attempt"] = result["extracted_at"]
    if result["status"] != "ok" and os.path.exists(out_path):
        previous = json.load(open(out_path))
        if previous.get("status") == "ok":
            previous["last_attempt"] = result["extracted_at"]
            previous["last_error"] = result.get("error", result["status"])
            result = previous
    tmp = out_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(result, f)
    os.replace(tmp, out_path)
    return {"id": hid, "status": result["status"], "n_codes": len(result.get("codes", {})),
            "seconds": result["seconds"], "error": result.get("error")}

def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    limit = int(opt("--limit", "0")) or None
    workers = int(opt("--workers", "6"))
    max_minutes = float(opt("--max-minutes", "240")) or None
    data_dir = opt("--data-dir", os.path.join(ROOT, "data"))
    registry_src = opt("--registry", REGISTRY_URL)
    only_ids = set(filter(None, (opt("--ids", "") or "").split(",")))
    max_bytes = int(opt("--max-mb", "1500")) * 1024 * 1024

    hosp_dir = os.path.join(data_dir, "hospitals")
    os.makedirs(hosp_dir, exist_ok=True)
    targets, _ = mrf_extract.load_codes(os.path.join(HERE, "target_codes.json"))
    recs = load_registry(registry_src)
    if only_ids:
        recs = [r for r in recs if r["id"] in only_ids]

    # stalest-first: no local file -> 0; else file mtime
    def staleness(r):
        p = os.path.join(hosp_dir, r["id"] + ".json")
        if not os.path.exists(p): return ""
        try:
            d = json.load(open(p))
            if d.get("mrf_url") != r["mrf_url"]: return ""
        except Exception:
            return ""
        return d.get("last_attempt", d.get("extracted_at", ""))
    unique = {}
    for r in recs:
        if not r["mrf_url"].startswith("http"): r["mrf_url"] = "https://" + r["mrf_url"]
        unique.setdefault(r["mrf_url"], r)
    recs = list(unique.values())
    recs.sort(key=staleness)
    if limit:
        recs = recs[:limit]

    print(f"[refresh] {len(recs)} hospitals to process, {workers} workers", flush=True)
    t0 = time.time()
    done = ok = 0
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process, r, targets, hosp_dir, max_bytes): r for r in recs}
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            done += 1
            ok += res["status"] == "ok"
            print(f"[{done}/{len(recs)}] {res['id']}: {res['status']} ({res['n_codes']} codes, {res['seconds']}s) {res.get('error') or ''}", flush=True)
            if max_minutes and (time.time() - t0) > max_minutes * 60:
                print(f"[refresh] time budget reached after {done} hospitals", flush=True)
                for f2 in futs: f2.cancel()
                break
    print(f"[refresh] done: {ok}/{done} ok", flush=True)

if __name__ == "__main__":
    main()
