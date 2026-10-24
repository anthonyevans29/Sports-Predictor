## 2026-10-23 (#660: 157-nhl-receipts — ARCHITECT addendum 157 item 2(a) and (b); read-only scripts, no model)
- scripts/nhl_gsax_feasibility.py: the GSAx feasibility receipt. Per season 2023-24..2025-26 and game type it prints:
  - the stored shot events by type, with and without a goalie_id;
  - the exclusions in the frozen xG rules' order, then the events kept but naming no goalie;
  - the one event set's shots faced, goals against and xG faced (v7's frozen fit), so the numerator and the denominator come from the same events;
  - the join of each event to the stored starters, and a boxscore cross-check per goalie-game;
  - per-goalie exposure for the regular season.
- scripts/nhl_starter_timing_probe.py: the starter timing probe, which reports the distribution (item 7). It polls the API's boxscore, landing and right-rail pages per game at T-120, T-90, T-60, T-45, T-35 (the cutoff), T-30, T-15 and puck drop, stamped by our clock. Per poll and side it records what each endpoint asserted and whether the side's identity is unique, conflicting or missing. It prints the share of games usable at the T-35 cutoff and the missing, conflicting, withdrawn and changed counts before puck drop. A T+20 read of the eventual starter checks reliability only. `--stored` counts the stored appearance rows captured before their game's start.
- Both open the DB read-only and never create one; neither writes a row. docs/CLI.md lists both.
