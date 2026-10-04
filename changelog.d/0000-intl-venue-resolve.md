## 2026-10-04 (intl-venue-resolve: venue-country normalization for the rows v3 left unknown; ARCHITECT lane 5, data lane)
- **Ruling (lane 5, 2026-10-04):** "Intl venue-country normalization for the 313 unmatched venues and the 57% unflagged rows. Data lane only; intl-elo-v2 stays frozen through its window."
- **`python cli.py intl-venue-resolve --from-dir <save> --venues-dir <dir> [--aliases FILE] [--plan]`**, for every `intl_match_venue` row with `neutral_v3` NULL:
  - route A `/venues?id=<id>` for venue ids outside the route-B catalog (the "unmatched venues"); one call per distinct id, `--max-calls` capped, saved as `venue_id_<id>.json` and replayed;
  - no venue id served: a UNIQUE city, then name, match against the saved `/venues` catalog; several countries = ambiguous, refused and counted;
  - country spelling: NFKD/casefold on both sides, plus an optional pinned `--aliases` JSON. None is built in (law 1). A neutral reading whose home-country spelling never appears as a venue country stays unknown ("alias needed"), and the receipt lists those spellings for a ruling.
- **Storage:** a NEW table `intl_venue_resolved` (created by `init_db`, additive; no migration) holding venue country, `country_source`, `neutral_resolved` and the reason a row stays unknown. `intl_match_venue` and intl-elo-v2's inputs are never touched (the frozen window holds).
- **Receipt:** the unknown-row reasons, route-A calls, outcomes per source, the unflagged share before → after, and the alias candidates.
- **Tests:** 4 new (plan, route A / city / name / ambiguity / spelling / home-unknown / unserved, v3 untouched, alias + replay with 0 calls, refusals, CLI plan). pytest 678 passed / 1 skipped.
