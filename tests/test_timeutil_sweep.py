"""Cosmetics lane C (architect 2026-09-29): the utcnow() -> now(UTC) sweep.
The replacements keep NAIVE UTC (the storage convention), and no deprecated
call remains in the repo's Python."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.timeutil import utc_naive_fromtimestamp, utc_now_naive

ROOT = Path(__file__).resolve().parents[1]


def test_helpers_are_naive_utc():
    n = utc_now_naive()
    assert n.tzinfo is None
    assert abs(n - datetime.now(timezone.utc).replace(tzinfo=None)) < timedelta(seconds=5)
    assert utc_naive_fromtimestamp(0) == datetime(1970, 1, 1)
    assert utc_naive_fromtimestamp(1790000000).tzinfo is None


def test_no_deprecated_utc_calls_remain():
    pat = re.compile(r"\.utc" + r"now\b|\.utc" + r"fromtimestamp\(")   # split so this file never matches itself
    hits = [f"{p.relative_to(ROOT)}:{i}" for p in ROOT.rglob("*.py")
            if "__pycache__" not in p.parts and ".git" not in p.parts
            for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1)
            if pat.search(line) and p.name != "timeutil.py"]
    assert hits == []


def test_schema_defaults_stamp_naive_utc():
    from src.db.schema import OddsSnapshot, Prediction
    for col in (OddsSnapshot.__table__.c.captured_at, Prediction.__table__.c.computed_at):
        v = col.default.arg(None) if col.default.is_callable else col.default.arg
        assert isinstance(v, datetime) and v.tzinfo is None
