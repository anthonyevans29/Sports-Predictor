**2026-10-06 — MLB adapter: statsapi's pre-game 0-0 is null on S / P / PW rows (law 4).**
- **Ruling (ARCHITECT, verbatim):** "SMALL, daily-class, separate PR: the MLB adapter passes statsapi's pre-game 0-0 through on SCHEDULED rows (the 21:23Z export carried actual scores 0 / 0 on LAD@ATL, 36 minutes before first pitch). When the coded state is S, P or PW, both scores are null (law 4). One test."
- **Built:** `_PREGAME_STATES = {S, P, PW}`; `_parse_game` nulls both scores for those states. An unmapped code still maps to SCHEDULED and is not touched; the ruling names three states.
- **Residual (read, not assumed):** the match upsert overwrites scores only when the feed sends one (`service.py`, "don't blank a finished match").
  - A game synced before this lands keeps its stored 0-0 until its first live or final score arrives.
  - That self-heals by first pitch. No DB write was made to clear it.
