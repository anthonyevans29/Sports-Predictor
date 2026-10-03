"""
K0 probe (2026-09-27, K-track opening) — READ-ONLY receipt of what a stored
Kalshi snapshot actually holds.

Question (architect): do yes_bid / yes_ask survive to the DB, or only a
derived probability? Code read (kalshi_sync -> KalshiAdapter.implied_prob):
only a derived prob is stored, in OddsSnapshot.devig_prob — the yes bid/ask
MIDPOINT, or the single present side, or last_price as a fallback. This
script prints the live table schema and real stored rows so the answer is a
receipt, not a claim.

Read-only: SELECT / PRAGMA only; opens the DB in SQLite read-only mode.
Run:  python3 scripts/k0_kalshi_storage_probe.py
Paste the whole output to the architect.
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(".env")
    url = os.getenv("DATABASE_URL", "sqlite:///./data/sports.db")
    if not url.startswith("sqlite:///"):
        print(f"✗ not a SQLite URL ({url.split(':')[0]}) — probe is SQLite-only. Stop.")
        return 1
    path = url.replace("sqlite:///", "")
    if not os.path.exists(path):
        print(f"✗ no database at {path}. Stop.")
        return 1
    con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)   # read-only (Windows/space-safe)
    cur = con.cursor()

    print("K0.1 — odds_snapshots schema (PRAGMA table_info)")
    for cid, name, typ, notnull, default, pk in cur.execute("PRAGMA table_info(odds_snapshots)"):
        print(f"  {cid:>2}  {name:<12} {typ:<12} notnull={notnull} pk={pk}")
    cols = [r[1] for r in cur.execute("PRAGMA table_info(odds_snapshots)")]
    price_cols = [c for c in cols if any(k in c.lower() for k in ("bid", "ask", "last", "price"))]
    print(f"  bid/ask/price columns present: {price_cols or 'NONE'}")

    print("\nK0.2 — kalshi snapshot counts by market")
    for market, n, first, last in cur.execute(
            "SELECT market, COUNT(*), MIN(captured_at), MAX(captured_at) FROM odds_snapshots "
            "WHERE source='kalshi' GROUP BY market ORDER BY market"):
        print(f"  market={market:<4} rows={n:<7} {first} .. {last}")

    print("\nK0.3 — one real stored row per market (latest), verbatim")
    con.row_factory = sqlite3.Row
    for (market,) in con.execute("SELECT DISTINCT market FROM odds_snapshots WHERE source='kalshi'"):
        row = con.execute(
            "SELECT s.*, c.code AS competition FROM odds_snapshots s "
            "JOIN matches m ON m.id = s.match_id JOIN competitions c ON c.id = m.competition_id "
            "WHERE s.source='kalshi' AND s.market=? ORDER BY s.captured_at DESC, s.id DESC LIMIT 1",
            (market,)).fetchone()
        print("  " + ", ".join(f"{k}={row[k]!r}" for k in row.keys()))

    print("\nK0 VERDICT: " + ("bid/ask columns EXIST" if any("bid" in c.lower() for c in price_cols)
                              else "bid/ask do NOT survive — only a derived prob (devig_prob) is stored"))
    print("Nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
