## 2026-10-13 (#505: cl-venue-stop — ARCHITECT addendum 61 item 3, #498)
- src/walters/desk_policy.py: CL makes no venue call. `SKEW_TEST_VENUE_COMPS = ("CL",)` stops `venue_edge` right after UNL's stop, with the ruled reason "three-way soccer — no venue call before the skew test is read (CL)", on the window card and in a CL fixtures file. Its own switch, `SKEW_TEST_VENUE_RULE`, is off only under `base_v11()`, for the frozen pre-F1c golden battery's CL rows, as every rule that postdates it is.
- src/walters/venue.py: `KALSHI_FEE_M["KXUCLGAME"] = (1.0, 1.0)` ("It costs a fill. It prices no call."). CL stays out of `KALSHI_SERIES_BY_COMPETITION`.
- tools/cockpit.html (the repo copy; republished only on the operator's word): the charter's "cups when priced" waits on the skew-test ruling, and the stop is named in the charter and the PASS-reason list.
- Tests: tests/test_cl_venue_stop.py (9); tests/test_cl_kalshi.py's two CL tests now read the stop and the fee entry.
