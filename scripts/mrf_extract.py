#!/usr/bin/env python3
"""Extract target CPT/HCPCS standard charges from one hospital MRF (45 CFR 180.50).

Usage: mrf_extract.py <mrf_url> <out.json> [--codes codes.json] [--max-bytes N]

Streams the file, supports CMS schema v2/v3 JSON, wide CSV, tall CSV, gzip and zip.
Never invents data: only rows matching the target code set are emitted, with the
dollar amounts exactly as published (negotiated percentages/algorithms are counted
but not converted to dollars).
"""
import csv, gzip, io, json, os, re, sys, tempfile, time, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CODES = os.path.join(HERE, "target_codes.json")

def load_codes(path):
    with open(path) as f:
        d = json.load(f)
    return {str(k): v for k, v in d["codes"].items()}, d.get("payer_canonical", {})

def norm_code(c):
    return re.sub(r"\s", "", str(c or "")).upper()

CPT_TYPE_RE = re.compile(r"^(CPT|HCPCS|CPT/HCPCS|CPT4|CPT®|CPT \(level 1\)|LEVEL 1 HCPCS/CPT)$", re.I)

PAYER_PATTERNS = [
    ("Medicare", r"medicare"),
    ("Medicaid", r"medicaid|medi-cal|medical assistance|\bmo healthnet\b|soonercare|masshealth|tenncare|apple health"),
    ("TRICARE", r"tricare|\bva\b|veterans"),
    ("Aetna", r"aetna"),
    ("Anthem BCBS", r"anthem"),
    ("BCBS", r"blue cross|blue shield|bcbs|bluecross|blueshield|premera|regence|highmark|horizon|excellus|carefirst|independence blue|florida blue|wellmark|capital blue|health care service|hcsc|\bbs of|blue of|arkansas blue|louisiana blue|carolina blue|vermont blue|hawaii medical service|\bhmcs\b"),
    ("Cigna", r"cigna|\bci general\b"),
    ("UnitedHealthcare", r"united\s*health|\buhc\b|united healthcare|optum|unitedbehavioral|\buha\b|\bumr\b|oxford health|sierra health|\buhic\b|golden rule"),
    ("Humana", r"humana"),
    ("Kaiser Permanente", r"kaiser"),
    ("Ambetter/Centene", r"ambetter|centene|\bceltic\b|illinicare|superior healthplan|\bsunshine health\b|\bpa health & wellness\b|meridian health"),
    ("Molina", r"molina"),
    ("Oscar", r"\boscar\b"),
    ("Aetna CVS", r"aetna better health"),
    ("AmeriHealth", r"amerihealth"),
    ("Healthfirst", r"healthfirst"),
    ("Emblem", r"\bemblem\b|\bgh\b|hip health"),
    ("Fidelis", r"fidelis"),
    ("MetroPlus", r"metroplus"),
    ("Blue Shield of California", r"blue shield of california"),
    ("Medi-Cal", r"medi-cal"),
]
_PAYER_RES = [(name, re.compile(pat, re.I)) for name, pat in PAYER_PATTERNS]

def canon_payer(payer, plan=""):
    s = f"{payer or ''} {plan or ''}"
    for name, rx in _PAYER_RES:
        if rx.search(s):
            return name
    return None

def clean_num(v):
    if v is None: return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f and abs(f) < 1e12 else None
    s = str(v).strip().replace("$", "").replace(",", "")
    if not s or s.lower() in ("n/a", "na", "null", "none", "-"): return None
    try:
        f = float(s)
        return f if abs(f) < 1e12 else None
    except ValueError:
        return None

class Acc:
    """Per-code accumulator."""
    __slots__ = ("desc", "cash", "gross", "smin", "smax", "payers", "pct_payers", "rows")
    def __init__(self):
        self.desc = None
        self.cash = []   # discounted_cash values
        self.gross = []
        self.smin = []
        self.smax = []
        self.payers = {}     # canon -> {"low":x,"high":y,"plans":set()}
        self.pct_payers = {} # canon -> count of percentage/algorithm-only entries
        self.rows = 0
    def add_charge(self, gross=None, cash=None, mn=None, mx=None):
        g, c = clean_num(gross), clean_num(cash)
        if g: self.gross.append(g)
        if c: self.cash.append(c)
        m1, m2 = clean_num(mn), clean_num(mx)
        if m1: self.smin.append(m1)
        if m2: self.smax.append(m2)
        self.rows += 1
    def add_payer(self, payer_name, plan_name, dollar=None, pct=None, algo=None):
        canon = canon_payer(payer_name, plan_name) or (str(payer_name).strip()[:60] if payer_name else None)
        if not canon: return
        d = clean_num(dollar)
        if d and d > 0:
            e = self.payers.setdefault(canon, {"low": None, "high": None, "plans": set()})
            if plan_name: e["plans"].add(str(plan_name)[:80])
            e["low"] = d if e["low"] is None else min(e["low"], d)
            e["high"] = d if e["high"] is None else max(e["high"], d)
        elif clean_num(pct) or (algo and str(algo).strip()):
            self.pct_payers[canon] = self.pct_payers.get(canon, 0) + 1
    def out(self):
        o = {"rows": self.rows}
        if self.desc: o["desc"] = self.desc
        if self.cash: o["cash_min"], o["cash_max"] = round(min(self.cash),2), round(max(self.cash),2)
        if self.gross: o["gross_min"], o["gross_max"] = round(min(self.gross),2), round(max(self.gross),2)
        if self.smin: o["neg_min"] = round(min(self.smin),2)
        if self.smax: o["neg_max"] = round(max(self.smax),2)
        if self.payers:
            o["payers"] = {k: {"low": round(v["low"],2), "high": round(v["high"],2), "plans": len(v["plans"])} for k, v in sorted(self.payers.items())}
        if self.pct_payers:
            o["pct_only_payers"] = self.pct_payers
        return o

# ---------------- streaming download ----------------

def download(url, max_bytes, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": "costofcare-research/1.0 (price transparency data collection)", "Accept-Encoding": "identity"})
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mrf")
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            while True:
                chunk = r.read(1 << 20)
                if not chunk: break
                total += len(chunk)
                if total > max_bytes:
                    raise OverflowError(f"file exceeds {max_bytes} bytes")
                tmp.write(chunk)
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise
    finally:
        tmp.close()
    return tmp.name, total

def open_payload(path):
    """Return (binary_fileobj, kind) where kind in json|csv; unwraps gzip/zip."""
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic[:2] == b"\x1f\x8b":
        f = gzip.open(path, "rb")
        head = f.read(4)
        f.seek(0) if hasattr(f, "seek") else None
        f = gzip.open(path, "rb")
    elif magic[:2] == b"PK":
        zf = zipfile.ZipFile(path)
        members = [m for m in zf.infolist() if not m.is_dir() and m.filename.lower().endswith((".csv", ".json", ".txt"))]
        if not members: raise ValueError("zip has no csv/json member")
        members.sort(key=lambda m: -m.file_size)
        f = zf.open(members[0], "r")
        head = f.read(4); f.close(); f = zf.open(members[0], "r")
    else:
        f = open(path, "rb")
        head = magic
    return f

# ---------------- JSON streaming ----------------

def iter_array_items(stream, array_key, chunk_size=1 << 20):
    """Yield raw JSON objects from a top-level array named array_key, streaming."""
    dec = json.JSONDecoder()
    buf = ""
    found = False
    eof = False
    def fill():
        nonlocal buf, eof
        data = stream.read(chunk_size)
        if not data:
            eof = True
            return False
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        buf += data
        return True
    fill()
    key = f'"{array_key}"'
    ki = buf.find(key)
    while ki < 0 and not eof:
        fill()
        ki = buf.find(key)
    if ki < 0:
        return
    buf = buf[ki + len(key):]
    # advance to '['
    while True:
        bi = buf.find("[")
        if bi >= 0:
            buf = buf[bi + 1:]
            break
        if eof: return
        fill()
    while True:
        # skip whitespace and commas
        i = 0
        n = len(buf)
        while i < n and buf[i] in " \t\r\n,":
            i += 1
        buf = buf[i:]
        if not buf:
            if eof: return
            fill(); continue
        if buf[0] == "]":
            return
        if buf[0] != "{":
            # unexpected; try to resync
            j = buf.find("{")
            if j < 0:
                if eof: return
                fill(); continue
            buf = buf[j:]
        while True:
            try:
                obj, end = dec.raw_decode(buf)
                break
            except json.JSONDecodeError:
                if eof:
                    raise ValueError("truncated or invalid JSON array")
                if not fill():
                    raise ValueError("truncated or invalid JSON array")
        yield obj
        buf = buf[end:]

# ---------------- extractors ----------------

def extract_json(f, targets):
    accs = {}
    meta = {}
    # metadata: read first ~64KB for hospital_name/location
    head = f.read(1 << 16)
    if isinstance(head, bytes):
        head = head.decode("utf-8", errors="replace")
    for k in ("hospital_name", "last_updated_on", "version"):
        m = re.search(r'"%s"\s*:\s*"([^"]*)"' % k, head)
        if m: meta[k] = m.group(1)
    m = re.search(r'"hospital_address"\s*:\s*\[\s*"([^"]*)"', head)
    if m: meta["hospital_address"] = m.group(1)
    # reopen via wrapper: we already consumed 64KB; chain remaining
    f2 = ChainTextReader(head, f)
    for item in iter_array_items(f2, "standard_charge_information"):
        codes = []
        for ci in item.get("code_information") or []:
            c = norm_code(ci.get("code"))
            if c in targets and CPT_TYPE_RE.match(str(ci.get("type", "")).strip()):
                codes.append(c)
        if not codes: continue
        desc = item.get("description")
        for sc in item.get("standard_charges") or []:
            for c in codes:
                a = accs.setdefault(c, Acc())
                if desc and not a.desc: a.desc = str(desc)[:160]
                a.add_charge(gross=sc.get("gross_charge"), cash=sc.get("discounted_cash"), mn=sc.get("minimum"), mx=sc.get("maximum"))
                for pi in sc.get("payers_information") or sc.get("payers") or []:
                    a.add_payer(pi.get("payer_name") or pi.get("payer"), pi.get("plan_name") or pi.get("plan"),
                                dollar=pi.get("standard_charge_dollar") if pi.get("standard_charge_dollar") is not None else pi.get("negotiated_dollar"),
                                pct=pi.get("standard_charge_percentage") if pi.get("standard_charge_percentage") is not None else pi.get("negotiated_percentage"),
                                algo=pi.get("standard_charge_algorithm") if pi.get("standard_charge_algorithm") is not None else pi.get("negotiated_algorithm"))
    return accs, meta

class ChainReader(io.RawIOBase):
    def __init__(self, head: bytes, rest):
        self._bufs = [io.BytesIO(head), rest]
    def readable(self): return True
    def readinto(self, b):
        while self._bufs:
            n = self._bufs[0].readinto(b) if hasattr(self._bufs[0], "readinto") else 0
            if n: return n
            self._bufs.pop(0)
        return 0

class ChainTextReader:
    def __init__(self, head: str, rest):
        self._head = io.StringIO(head)
        self._rest = rest
    def read(self, n=-1):
        if self._head is not None:
            a = self._head.read(n)
            if n is None or n < 0 or len(a) < n:
                rest_n = -1 if n is None or n < 0 else n - len(a)
                b = self._rest.read(rest_n)
                if isinstance(b, bytes): b = b.decode("utf-8", errors="replace")
                self._head = None
                return a + (b or "")
            return a
        b = self._rest.read(n)
        if isinstance(b, bytes): b = b.decode("utf-8", errors="replace")
        return b or ""

def sniff_csv(f, targets):
    """Read CMS metadata/header records with csv.reader (supports quoted newlines)."""
    meta = {}
    reader = csv.reader(f)
    keys = ("hospital_name", "last_updated_on", "version", "location_name", "hospital_address")
    for n, cells in enumerate(reader):
        if n > 30: raise ValueError("header row not found in first 30 CSV records")
        if not cells: continue
        first = cells[0].strip().lower().lstrip("\ufeff")
        if first == "hospital_name":
            vals = next(reader)
            for i,k in enumerate(cells):
                if k.strip() in keys and i < len(vals): meta[k.strip()] = vals[i].strip()
        elif "description" in [c.strip().lower() for c in cells] and any(re.fullmatch(r"code\|\d+",c.strip().lower()) for c in cells):
            return reader, [h.strip() for h in cells], meta
    raise ValueError("no header row found")

def extract_csv(f, targets):
    f, header, meta = sniff_csv(f, targets)
    lname = [h.lower() for h in header]
    idx = {h: i for i, h in enumerate(lname)}
    code_cols = [i for i, h in enumerate(lname) if re.fullmatch(r"code\|\d+", h)]
    code_type_cols = {h.split("|")[1]: i for i, h in enumerate(lname) if re.fullmatch(r"code\|\d+\|type", h)}
    gi = idx.get("standard_charge|gross")
    ci = idx.get("standard_charge|discounted_cash")
    mni = idx.get("standard_charge|min")
    mxi = idx.get("standard_charge|max")
    desci = 0 if lname and lname[0] == "description" else idx.get("description", 0)
    tall = "payer" in idx
    wide_payer_cols = []
    if not tall:
        for i, h in enumerate(lname):
            m = re.match(r"standard_charge\|(.+)\|negotiated_dollar$", h)
            if m:
                mid = m.group(1)
                parts = mid.split("|")
                payer, plan = parts[0], "|".join(parts[1:])
                wide_payer_cols.append((i, payer, plan))
    pi = idx.get("payer_name", idx.get("payer")); pli = idx.get("plan_name", idx.get("plan"))
    tall = pi is not None
    ndi = idx.get("standard_charge|negotiated_dollar")
    npi = idx.get("standard_charge|negotiated_percentage")
    nai = idx.get("standard_charge|negotiated_algorithm")
    accs = {}
    reader = f
    for row in reader:
        if len(row) < 5: continue
        matched = []
        for ci2 in code_cols:
            n = lname[ci2].split("|")[1]
            ti = code_type_cols.get(n)
            if ci2 < len(row):
                c = norm_code(row[ci2])
                if c in targets:
                    t = row[ti].strip() if ti is not None and ti < len(row) else "CPT"
                    if not ti or CPT_TYPE_RE.match(t) or t == "":
                        matched.append(c)
        if not matched: continue
        desc = row[desci][:160] if desci is not None and desci < len(row) else None
        def cell(i):
            return row[i] if i is not None and i < len(row) else None
        for c in set(matched):
            a = accs.setdefault(c, Acc())
            if desc and not a.desc: a.desc = desc
            a.add_charge(gross=cell(gi), cash=cell(ci), mn=cell(mni), mx=cell(mxi))
            if tall:
                a.add_payer(cell(pi), cell(pli), dollar=cell(ndi), pct=cell(npi), algo=cell(nai))
            else:
                for i2, payer, plan in wide_payer_cols:
                    v = row[i2] if i2 < len(row) else None
                    if v and clean_num(v):
                        a.add_payer(payer, plan, dollar=v)
    return accs, meta

def extract(path, targets):
    f = open_payload(path)
    # peek first non-space byte
    while True:
        b = f.read(1)
        if not b: raise ValueError("empty payload")
        if not b.isspace(): break
    if b == b"{":
        f = io.TextIOWrapper(io.BufferedReader(ChainReader(b, f), buffer_size=1 << 20), encoding="utf-8", errors="replace")
        return extract_json(f, targets)
    else:
        f = io.TextIOWrapper(io.BufferedReader(ChainReader(b, f), buffer_size=1 << 20), encoding="utf-8-sig", errors="replace", newline="")
        return extract_csv(f, targets)

def main():
    url, out = sys.argv[1], sys.argv[2]
    codes_path = DEFAULT_CODES
    max_bytes = 1500 * 1024 * 1024
    if "--codes" in sys.argv: codes_path = sys.argv[sys.argv.index("--codes") + 1]
    if "--max-bytes" in sys.argv: max_bytes = int(sys.argv[sys.argv.index("--max-bytes") + 1])
    targets, _ = load_codes(codes_path)
    t0 = time.time()
    result = {"mrf_url": url, "status": "failed", "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        path, total = download(url, max_bytes)
        result["bytes"] = total
        try:
            accs, meta = extract(path, targets)
        finally:
            os.unlink(path)
        result.update(meta)
        result["codes"] = {c: a.out() for c, a in sorted(accs.items()) if a.rows}
        result["status"] = "ok" if result["codes"] else "no_target_codes"
        result["seconds"] = round(time.time() - t0, 1)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"[:300]
        result["seconds"] = round(time.time() - t0, 1)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fo:
        json.dump(result, fo)
    print(json.dumps({"status": result["status"], "n_codes": len(result.get("codes", {})), "seconds": result["seconds"], "bytes": result.get("bytes"), "error": result.get("error")}))

if __name__ == "__main__":
    main()
