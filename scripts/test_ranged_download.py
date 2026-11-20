import http.server, os, re, threading, unittest
from unittest import mock
import mrf_extract as m

DATA = bytes(range(256)) * 40  # 10240 bytes


class Handler(http.server.BaseHTTPRequestHandler):
    etag = '"v1"'
    last_modified = None
    truncate_at = 4000
    ranged_status = None      # override status for ranged requests
    change_etag_after = None  # ranged request count after which ETag changes
    fail_first_ranges = 0     # drop connection this many times before serving a range
    declared = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        cls = type(self)
        rng = self.headers.get("Range")
        cls.requests.append(dict(self.headers))
        if rng is None:
            self.send_response(200)
            self.send_header("Content-Length", str(cls.declared or len(DATA)))
            if cls.etag: self.send_header("ETag", cls.etag)
            if cls.last_modified: self.send_header("Last-Modified", cls.last_modified)
            self.end_headers()
            self.wfile.write(DATA[:cls.truncate_at])
            return
        cls.range_count += 1
        if cls.ranged_status:
            self.send_response(cls.ranged_status)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if cls.fail_first_ranges > 0:
            cls.fail_first_ranges -= 1
            s, e = map(int, re.match(r"bytes=(\d+)-(\d+)", rng).groups())
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {s}-{min(e, len(DATA) - 1)}/{len(DATA)}")
            self.send_header("ETag", cls.etag)
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.write(b"x")
            return
        s, e = map(int, re.match(r"bytes=(\d+)-(\d+)", rng).groups())
        e = min(e, len(DATA) - 1)
        etag = cls.etag
        if cls.change_etag_after is not None and cls.range_count > cls.change_etag_after:
            etag = '"v2"'
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {s}-{e}/{len(DATA)}")
        self.send_header("Content-Length", str(e - s + 1))
        if etag: self.send_header("ETag", etag)
        if cls.last_modified: self.send_header("Last-Modified", cls.last_modified)
        self.end_headers()
        self.wfile.write(DATA[s:e + 1])


class RangedDownloadTests(unittest.TestCase):
    def setUp(self):
        class H(Handler):
            requests = []
            range_count = 0
        self.H = H
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/f"
        self.paths = []
        p1 = mock.patch.object(m, "RESUME_CHUNK", 3000)
        p2 = mock.patch.object(m.time, "sleep")
        p1.start(); self.sleep = p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()
        for p in self.paths:
            if os.path.exists(p): os.unlink(p)

    def test_resume_completes(self):
        path, total, ev = m.download(self.url, 1 << 20, timeout=5)
        self.paths.append(path)
        with open(path, "rb") as f: self.assertEqual(f.read(), DATA)
        self.assertEqual(total, len(DATA))
        self.assertEqual(ev, {"method": "ranged-content-range-verified", "expected": len(DATA), "received": len(DATA)})
        ranged = [r for r in self.H.requests if "Range" in r]
        self.assertEqual([r["Range"] for r in ranged], ["bytes=4000-6999", "bytes=7000-9999", "bytes=10000-10239"])
        self.assertTrue(all(r["If-Range"] == '"v1"' for r in ranged))

    def test_resume_with_last_modified_only(self):
        self.H.etag = None
        self.H.last_modified = "Wed, 01 Jan 2025 00:00:00 GMT"
        path, _, ev = m.download(self.url, 1 << 20, timeout=5)
        self.paths.append(path)
        self.assertEqual(ev["method"], "ranged-content-range-verified")
        self.assertEqual(self.H.requests[-1]["If-Range"], self.H.last_modified)

    def test_retry_with_backoff_then_success(self):
        self.H.fail_first_ranges = 2
        path, _, ev = m.download(self.url, 1 << 20, timeout=5)
        self.paths.append(path)
        with open(path, "rb") as f: self.assertEqual(f.read(), DATA)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1, 2])

    def test_retry_exhaustion_names_range(self):
        self.H.fail_first_ranges = 99
        with self.assertRaises(m.IncompleteDownloadError) as cm:
            m.download(self.url, 1 << 20, timeout=5)
        self.assertIn("bytes=4000-6999", str(cm.exception))
        self.assertEqual(self.H.range_count, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1, 2])

    def test_etag_changes_mid_download(self):
        self.H.change_etag_after = 1
        with self.assertRaises(m.IncompleteDownloadError) as cm:
            m.download(self.url, 1 << 20, timeout=5)
        self.assertIn("entity changed", str(cm.exception))

    def test_non_206_aborts(self):
        for status in (200, 416, 429, 403):
            with self.subTest(status=status):
                self.H.ranged_status = status
                self.H.range_count = 0
                with self.assertRaises(m.IncompleteDownloadError) as cm:
                    m.download(self.url, 1 << 20, timeout=5)
                self.assertIn(f"status={status}", str(cm.exception))
                self.assertEqual(self.H.range_count, 1)

    def test_no_validator_no_ranged_attempt(self):
        self.H.etag = None
        with self.assertRaises(m.IncompleteDownloadError) as cm:
            m.download(self.url, 1 << 20, timeout=5)
        self.assertIn("expected 10240 bytes, received 4000", str(cm.exception))
        self.assertEqual(self.H.range_count, 0)

    def test_declared_total_over_max_bytes(self):
        with self.assertRaises(OverflowError) as cm:
            m.download(self.url, 5000, timeout=5)
        self.assertEqual(str(cm.exception), "file exceeds 5000 bytes")
        self.assertEqual(self.H.range_count, 0)

    def test_no_truncation_unchanged(self):
        self.H.truncate_at = len(DATA)
        path, total, ev = m.download(self.url, 1 << 20, timeout=5)
        self.paths.append(path)
        self.assertEqual(ev, {"method": "content-length", "expected": len(DATA), "received": len(DATA)})
        self.assertEqual(self.H.range_count, 0)


if __name__ == "__main__":
    unittest.main()
