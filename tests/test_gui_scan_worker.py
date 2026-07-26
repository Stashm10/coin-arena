import threading

from arena.gui.scan_worker import run_scan
from arena.models import Finding, ScanResult
from arena.settings import Settings


def _result():
    return ScanResult("M" * 44, "AVOID",
                      [Finding("authorities", "DISQUALIFIER", "x", {})],
                      0, None, "T", 1.0)


def test_on_done_called_with_result():
    done = threading.Event()
    holder = {}

    def on_done(r):
        holder["r"] = r
        done.set()

    t = run_scan("mint", Settings("k"), on_done, lambda e: None,
                 scan_fn=lambda m, s: _result())
    assert done.wait(timeout=5)
    t.join(timeout=5)
    assert holder["r"].verdict == "AVOID"


def test_on_error_called_on_exception():
    failed = threading.Event()
    holder = {}

    def on_error(exc):
        holder["exc"] = exc
        failed.set()

    def boom(m, s):
        raise RuntimeError("scan blew up")

    run_scan("mint", Settings(None), lambda r: None, on_error, scan_fn=boom)
    assert failed.wait(timeout=5)
    assert isinstance(holder["exc"], RuntimeError)


def test_returns_started_thread():
    t = run_scan("mint", Settings("k"), lambda r: None, lambda e: None,
                 scan_fn=lambda m, s: _result())
    assert isinstance(t, threading.Thread)
    t.join(timeout=5)
