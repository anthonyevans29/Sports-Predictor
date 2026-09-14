# Diagnostic: what season/status/date are the WC matches actually stored with?
from src.db.database import session_scope
from src.db.schema import Competition, Match
from sqlalchemy import select, func
from datetime import datetime

with session_scope() as s:
    comp = s.execute(select(Competition).where(Competition.code=="WC")).scalar_one_or_none()
    if not comp:
        print("No WC competition row!"); raise SystemExit
    print(f"WC competition id={comp.id} type={comp.type}")
    rows = list(s.execute(select(Match).where(Match.competition_id==comp.id)).scalars())
    print(f"Total WC matches: {len(rows)}")
    from collections import Counter
    print("season values:", Counter(m.season for m in rows))
    print("status values:", Counter(str(m.status) for m in rows))
    now = datetime.utcnow()
    future = sum(1 for m in rows if m.utc_date and m.utc_date >= now)
    print(f"matches with utc_date >= now: {future}")
    # earliest few dates
    dated = sorted([m.utc_date for m in rows if m.utc_date])[:5]
    print("earliest match dates:", [d.isoformat() for d in dated])
    # do they have odds source ids?
    with_src = sum(1 for m in rows if (m.external_ids or {}).get("api_football"))
    print(f"matches with api_football external_id: {with_src}")
    # sample external_ids keys
    if rows:
        print("sample external_ids:", rows[0].external_ids)
