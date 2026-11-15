**2026-11-15 — `nhl-goalie-coverage --db COPY`: the counts-only NHL season receipt (addendum 386 item 2; #1012).**
- **Ruling (verbatim in part):** "THE NHL COVERAGE RECEIPT — RULED: ADD --db, AND I RUN IT ON A COPY ... --db COPY through the shared fence, opened mode=ro with immutable=1, with NO init_db() on that path; the command without --db is unchanged ... No goalie's name and no figure of any model."
- **What landed:** the receipt (a)–(e) by season, 2023-24 to 2026-27, from the stored appearances alone.
- **The definitions:**
  - a game is one nhl_game_id;
  - the season comes from its stored start, UTC, 1 July to 30 June;
  - the regular season is game type 2 as the rows say it, never inferred;
  - flagged means exactly one starter row on a side;
  - relief means another goalie with TOI > 0.
- **Next:** the architect writes the laptop block; the command and its one argument are named in #1012.
