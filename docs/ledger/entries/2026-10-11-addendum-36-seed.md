**2026-10-11 — FINDING + RULING + RECEIPT (ARCHITECT 2026-10-10 06:57 ET, addendum 36 items 1, 3 and 4; Issue #410): the host's soccer model runs on the wrong ratings; the seed (B4) is amended; the rating coverage receipt.**
- **Header (verbatim):**
  > ARCHITECT · 2026-10-10 06:57 ET · addendum 36 · FINDING: the host's soccer model runs on the wrong ratings. Two
  > rulings: a default rating is labelled and gets no call; the seed (B4) is amended. Behind addenda 33, 34, 35
- **Finding, item 1 (verbatim):**
  > 1. FINDING: ON THE HOST, EVERY PL TEAM'S RATING IS THE DEFAULT OR ANOTHER CLUB'S. A BACKLOG entry and an Issue
  > (finding, soccer); nothing is built by this item. The receipt is at the end, read from the mirror at 1bbbe62.
  > - The host's two PL files with rows, 2026-10-09 14:01Z and 2026-10-10 09:31Z, both v1.3.0, ten games each: of 20
  >   team slots, 16 read rating 1500.0 with league null, and 4 read some other league's club (CZE, GRE, BEL, SA).
  >   The laptop's file of 2026-10-09 22:12Z reads PL in 20 of 20.
  > - From the code. The production soccer row keeps its league ratings and its team_to_league under team ids
  >   (training.py:222-251, read back at :439-449 and used at :670-677), and EloState.get answers the starting
  >   rating for an id it does not hold (src/models/elo.py:67-68).
  > - From the spec. hosting-h1.md B2 (:258-259) and B4 (:424-431) installed the laptop's production model_versions
  >   rows on the host, every column, verified by hash, into a database whose teams the host's own bootstrap had
  >   created under other ids. By that mechanism it has been so since the seed.
  > - So the host's soccer model numbers are wrong, and nothing in a row says so. The attack and defence strengths
  >   are right: they come from the host's own matches and equal the laptop's to three decimals in all ten games.
  > - NFL is not touched: on the one game both machines exported on 2026-10-08 they agree at 0.6371.
  > - No call of record is affected. The laptop is the writer of record and no host file has been read as a call.
  >   But the host's hourly card carries these PL rows (with_model 6 at 10:09Z today), and its pager reads the card.
- **Ruling, item 3 (verbatim):**
  > 3. RULED: THE SEED (B4) IS AMENDED.
  > "The production soccer row's ratings and team_to_league are keyed by the team ids of the database that trained
  > them. They are that database's state, not configuration, and a seeded copy is valid only where the team ids are
  > the same. On the host they are not. Nothing is re-keyed there: the cutover replaces that database with the
  > laptop's. Until then the host's soccer model rows are evidence of nothing, I name them in the compare as a class
  > of their own, and no page built from them is a call."
  > - hosting-h1.md B4 gains that paragraph and this finding's Issue number.
  > - The cutover runbook gains one check, after the install and before the writer flag flips: "the host exports
  >   the PL predictions from the installed database, and the file equals the laptop's last file from that
  >   database, number for number."
- **Item 4 (verbatim):**
  > 4. A READ-ONLY RECEIPT, small: scripts/soccer_rating_coverage.py --competition CODE --season S. For each team of
  > that competition and season: its id, its name, its rating in the production model's league table or MISSING, and
  > its team_to_league. Then the totals. The operator runs it on both machines, and both consoles go on the Issue.
- **Order, item 5 (verbatim):**
  > 5. ORDER. Addendum 33's two commits first: the tag waits for #401. Then item 2 here: I want it on main before
  > that tag, so that the host stops calling on rows it cannot rate. Then addendum 34 item 7, addendum 35, and
  > items 1, 3 and 4 here.
- **Receipt (item 1, verbatim):**
```
RECEIPT (item 1), from the mirror at 1bbbe62:
soccer_PL_2026-10-10_to_2026-10-13.json, three pushes; team slots = 2 per game:
  host   2026-10-09 · exported_at 2026-10-09T14:01:09Z · git_sha 0023368
      games 10 · slots 20: 1500.0 and league null 16 · other league 4 · PL 0
  host   2026-10-10 · exported_at 2026-10-10T09:31:03Z · git_sha 0023368
      games 10 · slots 20: 1500.0 and league null 16 · other league 4 · PL 0
  laptop 2026-10-09 · exported_at 2026-10-09T22:12:07Z · git_sha ed5ecbb
      games 10 · slots 20: 1500.0 and league null 0 · other league 0 · PL 20
per game: home rating (league) / away rating (league) · model home/draw/away · desk call
  host   30699 Leeds @ Arsenal             1500.0 (null) / 1500.0 (null) · 0.3533/0.3447/0.3020 · PASS
  laptop  9219 Leeds @ Arsenal             1705.5 (PL) / 1575.0 (PL) · 0.3810/0.3420/0.2769 · PASS
  host   30700 Bournemouth @ Chelsea       1500.0 (null) / 1500.0 (null) · 0.4648/0.2548/0.2803 · PASS
  laptop  9220 Bournemouth @ Chelsea       1530.3 (PL) / 1556.0 (PL) · 0.4169/0.2682/0.3148 · PASS
  host   30701 Fulham @ Ipswich            1500.0 (null) / 1544.9 (CZE) · 0.4037/0.2720/0.3243 · PASS
  laptop  9222 Fulham @ Ipswich            1542.4 (PL) / 1497.1 (PL) · 0.4278/0.2698/0.3024 · PASS
  host   30702 Brentford @ Aston Villa     1500.0 (null) / 1500.0 (null) · 0.2080/0.2940/0.4981 · PASS
  laptop  9224 Brentford @ Aston Villa     1539.2 (PL) / 1573.1 (PL) · 0.2021/0.2915/0.5064 · LADDER
  host   30703 Brighton @ Sunderland       1500.0 (null) / 1500.0 (null) · 0.1877/0.2386/0.5737 · LADDER
  laptop  9225 Brighton @ Sunderland       1504.9 (PL) / 1616.2 (PL) · 0.1677/0.2285/0.6037 · LADDER
  host   30704 Tottenham @ Man United      1677.5 (GRE) / 1500.0 (null) · 0.4965/0.3078/0.1956 · PASS
  laptop  9217 Tottenham @ Man United      1597.6 (PL) / 1435.4 (PL) · 0.5001/0.3092/0.1907 · PASS
  host   30705 Nottm Forest @ Crystal Palace 1500.0 (null) / 1500.0 (null) · 0.2534/0.3014/0.4452 · PASS
  laptop  9221 Nottm Forest @ Crystal Palace 1480.7 (PL) / 1532.7 (PL) · 0.2433/0.2988/0.4579 · PASS
  host   30706 Everton @ Hull City         1500.0 (null) / 1500.0 (null) · 0.2739/0.3724/0.3537 · PASS
  laptop  9223 Everton @ Hull City         1541.7 (PL) / 1536.2 (PL) · 0.2748/0.3726/0.3526 · PASS
  host   30707 Man City @ Liverpool        1500.0 (null) / 1462.6 (BEL) · 0.2647/0.2947/0.4406 · PASS
  laptop  9218 Man City @ Liverpool        1608.7 (PL) / 1714.0 (PL) · 0.2361/0.2875/0.4764 · PASS
  host   30708 Newcastle @ Coventry        1624.5 (SA) / 1500.0 (null) · 0.2119/0.3107/0.4774 · PASS
  laptop  9226 Newcastle @ Coventry        1567.1 (PL) / 1539.0 (PL) · 0.1404/0.2436/0.6160 · LADDER

===== addendum 37 (2026-10-10 08:27 ET; CORRECTED 2026-10-11 07:08 ET receipt B row 32810) — full text relayed in-session; see transcript.
```
- **Built:**
  - docs/specs/hosting-h1.md B4 carries the item 3 paragraph and #410.
  - docs/specs/h2-cutover-runbook.md section 1 step 4: after `install`, before `flip`, the PL export check (the steps run one at a time on cutover day; the host's file in a fresh directory, `--status scheduled`, the reference's own dates; `compare_exports.py` on the two directories, VERDICT: CLEAN, else the cutover stops before `flip`).
  - `scripts/soccer_rating_coverage.py` (read-only).
  - Item 2 (the default-rating label and PASS) is #411.
- **Codex round 1 on #417 (fixed):** the host's export goes to a fresh directory (`install` copies the laptop's exports into `exports/`, so the reference could otherwise compare against itself); `--start` / `--end` come from the reference's file NAME (calendar dates, `--end` inclusive, the chain's own arguments), not its JSON `start_date` / exclusive `end_date`; `--status scheduled`, the chain's own; the coverage receipt keeps a match-side id with no team row.
- **Readings:** the runbook check uses `compare_exports.py` as "number for number": it masks only timestamp-like keys and `match_id` (machine-local), keys rows on (kickoff, home, away), and is CLEAN only when every other field is identical. "Team of that competition and season" in the receipt is every team id in that competition's stored matches of that season.
- **Run order (operator, both machines, on the architect's word):** `python3 scripts/soccer_rating_coverage.py --competition PL --season 2026/27`; both consoles on #410.
- **Receipts:** tests/test_soccer_rating_coverage.py (4 tests): ratings or MISSING and team_to_league per team of the competition-season only, totals, the legacy single-state shape, refusal on zero or two production rows, the file byte-identical after a run.
