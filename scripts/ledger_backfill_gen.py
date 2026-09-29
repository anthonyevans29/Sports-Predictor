"""(Run from the repo root: python scripts/ledger_backfill_gen.py <ledger BACKLOG commit>.)
Build .github/ledger/backfill.json: resolve every item's BACKLOG heading to
the commit that introduced it and its line at that commit (law 1)."""
import json
import subprocess

PHASE_A = "eed69bd3b83c4d152ca475b896499dc3ae1d01e6"   # claude/mlb-phase-a-adapter (#73)
CUT, POL, EXE = "Cutover ~Oct 8", "Policy v1.2 promotion (30 value shadows)", "Executable-edge ruling (2 wks of ladders)"
OFF, NHL, CUP = "Offseason decisions (MLB egress/provider)", "NHL reopening (goalie source)", "Cup reopening (rotation R-track)"


def I(key, title, track, cls, sport, size, heading, summary, reopening=None, milestone=None, flags=(),
      ref="main", due=None, anchor=None):
    return dict(anchor=anchor, key=key, title=title, track=track, cls=cls, sport=sport, size=size, flags=list(flags),
                milestone=milestone, due=due, heading=heading, ref=ref, summary=summary, reopening=reopening)


ITEMS = [
    # ---- the queue, in CLAUDE.md's order (re-ranked 2026-09-26; v0.4 built) ----
    I("k-track", "K-track: Kalshi-executable edge accounting (fee-adjusted floors, liquidity-aware sizing)",
      "K", "lane", "all", "L", "MISSION DECLARED 2026-09-26",
      "Queue #2 (opened 2026-09-26). The K1 data layer and the informational K2 exec-edge display have shipped. "
      "Remaining: model_p vs the stored ask, fee-adjusted edge floors, and liquidity-aware sizing. The spec comes "
      "from the architect.", milestone=EXE),
    I("b-track", "B-track: bankroll doctrine (daily exposure cap, drawdown circuit-breaker, cross-ticket correlation)",
      "B", "lane", "all", "L", "MISSION DECLARED 2026-09-26",
      "Queue #3 (opened 2026-09-26). The spec comes after K."),
    I("t-track", "T-track: scheduler spec", "T", "lane", "all", "L", "HOSTING H0 DRAFT 2026-09-26",
      "Queue #4. It holds its place behind K and B."),
    I("lineup-probe", "Lineup-history probe receipt (cup R-track reopening groundwork)", "R", "probe", "cups", "S",
      "Lineup-history PROBE shipped 2026-09-26",
      "Queue #5. `scripts/lineup_history_probe.py` shipped read-only. The receipt (Anthony's real run) decides "
      "what as-of lineup data a rotation-aware cup candidate could use.",
      milestone=CUP, flags=["needs-operator"]),
    I("ncaa-model", "NCAA model (own gate, no deadline)", "model", "lane", "ncaa", "L", "NCAA TRACK OPENED 2026-09-25",
      "Queue #6. Market-only doctrine stands (Kalshi is the primary college market). A model needs its own frozen "
      "gate first."),
    I("u2-enrichment", "U2 export enrichment: model-internals \"why\" fields + NFL kalshi field", "ops", "lane", "nfl",
      "M", "U2 — NFL EXPORT \"WHY\" FIELDS 2026-09-27",
      "Queue #6. The additive NFL why-fields shipped 2026-09-27; the remaining model-internals fields and the NFL "
      "kalshi field are queued."),
    I("s14-stage2", "S14 Stage-2: totals under-compression in uncertain-winner games", "model", "lane", "soccer", "M",
      "S14. Totals under-compression in uncertain-winner games",
      "Queue #6. Stage 1 is complete; Stage 2 follows the pre-committed test."),
    I("snapshot-pruning", "Snapshot pruning / rollup design", "ops", "lane", "all", "M",
      "#63 DECISIONS RULED + ANCHOR TIMESTAMP ON EVERY GRADE",
      "Queue #6. Snapshot growth was accepted (ruling (d) on #63); the cap rides this queued design."),
    I("s19-time-decay", "S19: time-decay match weighting (soccer candidate, existing gate)", "model", "lane", "soccer",
      "M", "DEEP-RESEARCH DISPOSITION (architect, 2026-09-25)",
      "Queue #7 (tail). A soccer candidate through the existing gate, after the cup unlock + NHL v3."),
    I("s20-rps", "S20: RPS reported alongside log-loss in the soccer backtest (metric only)", "model", "lane",
      "soccer", "S", "DEEP-RESEARCH DISPOSITION (architect, 2026-09-25)",
      "Queue #7 (tail). A reported metric only: the bars are unchanged."),
    # ---- dated / condition-bound lanes ----
    I("cutover", "H2 cutover: the decision after the parallel week + the ONE .backup migration", "ops", "lane", "all",
      "L", "H1b DAY ONE 2026-09-28 13:45 UTC",
      "The parallel week started 2026-09-28 13:45 UTC. The earliest cutover decision is after 2026-10-05 13:45 UTC "
      "(criterion 1: 7/7 days with every host timer firing). The frozen criteria are unchanged; the laptop stays "
      "writer of record until then.", milestone=CUT),
    I("policy-v12", "Policy v1.2 promotion: value-side shadow after 30 graded", "policy", "lane", "all", "M",
      "VALUE-SIDE SHADOW (policy v1.2 CANDIDATE)",
      "The Desk logs `value_shadow` calls at 0 units. Promotion only via a POLICY_VERSION bump after >= 30 graded "
      "value shadows (the counter is in the P&L block).", milestone=POL),
    I("exec-edge-ruling", "Executable-edge ruling after 2 weeks of ladders", "K", "lane", "all", "M",
      "K2: EXECUTABLE-EDGE DISPLAY",
      "K2's exec edge (model p - kalshi_exec_cost) is INFORMATIONAL: calls, units and tiers are unchanged. The ruling "
      "on using it comes after 2 weeks of ladders.", milestone=EXE, flags=["needs-ruling"]),
    # ---- findings / pending rulings ----
    I("fee-rounding", "Kalshi fee rounding: per-contract cent ceiling overstates the fee by up to ~1c", "K", "finding",
      "all", "S", "KALSHI FEE SCHEDULE: VERIFY RECEIPT + K2 JOIN BID",
      "`venue.kalshi_fee` ceils per contract to the cent; Kalshi rounds per order to the centicent. At P = 0.60 the "
      "exact fee is 1.68c and we model 2c (exec_cost +0.32pp too high). Code unchanged pending the ruling: move to the "
      "exact 0.07*P*(1-P)?", milestone=EXE, flags=["needs-ruling"]),
    I("no-side-price", "Derived NO-side exec price for away picks", "K", "finding", "all", "S",
      "KALSHI FEE SCHEDULE: VERIFY RECEIPT + K2 JOIN BID",
      "Exported quotes are the HOME contract's, so an AWAY side shows \"exec —\". A NO-side price (1 - home bid + fee) "
      "could be derived; not built, because it is a guess until the away contract's own quotes are stored.",
      milestone=EXE, flags=["needs-ruling"]),
    I("mve-combos", "MVE combos: mixed legs stay off_book_other; verify the MVE title grammar", "K", "finding", "all",
      "S", "LANE C: COSMETICS (architect Tuesday authorization, 2026-09-29)",
      "MVE combo fills are classified by leg content. ARCHITECT-VERIFY: the title grammar (no real MVE CSV seen). "
      "ARCHITECT-RULE: do mixed combos stay off_book_other?", flags=["needs-ruling"]),
    I("venue-edge-stale", "Venue-edge on NFL rides possibly stale book moneylines: exclude outright?", "policy",
      "finding", "nfl", "S", "COCKPIT v0.4 BUILT",
      "v0.4 OPEN QUESTION: such calls carry the rule tag \"venue gap >= 8pp (STALE-BOOK? zone)\" so attribution "
      "separates them; excluding them outright is the architect's call.", flags=["needs-ruling"]),
    I("soccer-n30", "Soccer positive-edge cohort: the n=30 pre-committed read", "model", "finding", "soccer", "S",
      "POLICY v1.0 — KNOBS RETIRED 2026-09-25",
      "The positive-edge cohort (>= +5pp vs market) stood at 6/16; big anti-market edges are anti-predictive. The "
      "pre-committed read happens at n=30. Market-first discipline is doctrine meanwhile."),
    # ---- operator actions ----
    I("kalshi-maker-m", "Kalshi maker multiplier M for the game series: paste the PDF rows", "K", "operator-action",
      "all", "S", "KALSHI FEE SCHEDULE: VERIFY RECEIPT + K2 JOIN BID",
      "NOT VERIFIED: the maker multiplier for KXNFLGAME / KXNCAAFGAME / KXMLBGAME / KXNHLGAME / the soccer series lives "
      "in the fee PDF's per-series table, which this environment cannot open. Paste the rows, or allow kalshi.com in "
      "the environment's network settings.", milestone=EXE, flags=["needs-operator"]),
    I("t90-journal", "Host journal receipt for Monday's T-90 check", "ops", "operator-action", "nfl", "S",
      "MNF QB AUDIT VERDICT + LINE-MOVE ALARM",
      "Expected: window_page at 22:05 / 23:05 / 00:05 with t90_news 0, empty freshen_needed, no freshen receipt. "
      "Commands are in #65.", milestone=CUT, flags=["needs-operator"]),
    I("phase-a-host", "MLB PHASE A: run the one-time live-host sequence + paste the status_vocab line", "ops",
      "operator-action", "mlb", "S", "MLB PHASE A BUILT", ref=PHASE_A,
      summary="After #73 merges: the runbook's one-time sequence (backup, seasons 2025 + 2026, enable "
      "sp-mlb-history.timer); paste both MLB-FALLBACK-RECEIPT lines; then the fingerprint compare without "
      "--skip-family MLB, with --waive \"MLB:2025:apisports doubleheader gap\" (ruling (4) on #73).", milestone=CUT, flags=["needs-operator"]),
    # ---- known limitations (Waiting on condition) ----
    I("dh-game2", "api-sports omits doubleheader game 2 (13 games, 2025-2026)", "ops", "limitation", "mlb", "S",
      "MLB PHASE A BUILT", ref=PHASE_A,
      summary="api-sports /games lists no doubleheader game 2 (13 games across two seasons, all confirmed same-date / "
      "same-teams). The fallback never fabricates them; existing rows are marked \"apisports-unavailable\"; the "
      "laptop's statsapi remains the record. On the host they are simply absent; the compare WAIVES them with "
      "reason \"apisports doubleheader gap\" (ruled on #73, a provider-difference class).",
      reopening="The provider starts listing doubleheader game 2, or the host gains statsapi egress (a residential "
      "exit node) — the offseason egress/provider decision.", milestone=OFF),
    I("mlb-laptop-only", "MLB predictions are laptop-only (PHASE B negative)", "ops", "limitation", "mlb", "M",
      "MLB PHASE A BUILT", ref=PHASE_A,
      summary="PHASE B closed NEGATIVE: api-sports Baseball has no pitcher / bullpen / umpire / lineup / injury "
      "endpoints (control passed). The host holds no MLB predictions; the host MLB timers stay off.",
      reopening="Residential egress for statsapi (a home exit node) or a new provider — decided in the offseason.",
      milestone=OFF),
    I("soccer-lm-kalshi", "Soccer line-move alarm is Kalshi-only (no book snapshots)", "ops", "limitation", "soccer",
      "S", "LATE-NEWS FOLLOW-ON: T-90 HOLE",
      "The line-move alarm reads stored snapshots; soccer has no book consensus snapshots, so only Kalshi moves count.",
      reopening="Accepted limit. Reopens if soccer sync-odds starts appending a book consensus to odds_snapshots "
      "(the NFL #63 pattern)."),
    I("mlb-lm-cadence", "MLB line-move resolution follows the capture-odds cadence", "ops", "limitation", "mlb", "S",
      "LATE-NEWS FOLLOW-ON: T-90 HOLE",
      "MLB book snapshots exist only at capture-odds runs, so a move between captures is seen late or netted out.",
      reopening="Accepted limit. Reopens with a denser MLB capture cadence or a per-sync consensus append."),
    I("injury-latency", "Provider injury-report latency (MNF QB audit)", "ops", "limitation", "nfl", "S",
      "MNF QB AUDIT VERDICT + LINE-MOVE ALARM",
      "Verdict: CAUSE = SYNC TIMING + PROVIDER LATENCY (Williams absent from the report at both syncs). Mitigations "
      "shipped: imminent-tier injury sync, the line-move alarm, the T-60 closing-freshen doctrine.",
      reopening="Accepted limit. Reopens with a faster injury source."),
    I("magicdns", "Mac MagicDNS does not resolve tailnet names (unverified client side)", "ops", "limitation", "all",
      "S", "H1b DAY ONE 2026-09-28 13:45 UTC",
      "Tailscale SSH is enabled server-side; the tailnet-IP door is proven and is the STANDARD. MagicDNS on the Mac "
      "is unverified.", reopening="Retest after a Mac reboot; the 100.x IP stays the standard meanwhile.",
      milestone=CUT, flags=["needs-operator"], anchor="MagicDNS isn't resolving"),
    I("ncaa-spread-ref", "NCAA spread fallback at INSUFFICIENT-REF", "K", "limitation", "ncaa", "S",
      "STALE-BOOK? LIE DETECTOR",
      "Vetted verdict NCAA INSUFFICIENT-REF (n=8, 3.05pp vs the frozen 3.0pp bar); disposition: accumulate "
      "naturally. FALLBACK_LIVE stays False.",
      reopening="Vetted n >= 10: re-run `spread-fallback-check --competition NCAA`; a vetted PASS flips the switch "
      "(a one-line PR)."),
    I("nfl-spread-dark", "NFL spread fallback dark (FAIL; moneylines stale at source)", "K", "limitation", "nfl", "S",
      "SPREAD-FALLBACK MEASUREMENT REVISION + DARK SWITCH",
      "Acceptance FAIL ratified (NFL 5.54pp vs 3.0pp); catastrophic rows survived vetting, implying stale "
      "moneylines at source. FALLBACK_LIVE = False.",
      reopening="Only a vetted PASS flips it; sign disagreements are data problems, not sigma problems."),
    I("unresolved-positions", "Unresolved-position players outside the roster lookup", "ops", "limitation", "nfl", "S",
      "MNF QB AUDIT VERDICT + LINE-MOVE ALARM",
      "Ruling (4): the 9 unresolved positions are practice-squad/IR players outside the roster lookup; the export's "
      "`positions_unresolved` makes them visible.",
      reopening="Accepted limit. Reopens if the provider's /injuries carries position or the roster covers PS/IR."),
    I("nhl-model-suspended", "NHL model track suspended (schedule-only floor ~0.691)", "model", "limitation", "nhl",
      "L", "NHL PHASE 2 CLOSED — MODEL TRACK SUSPENDED",
      "v1-v4 all FAILED vs the 0.6866 bar; NHL runs MARKET-ONLY. The goalie probe was NEGATIVE: the hockey provider "
      "has no goalie/lineup data.",
      reopening="An EXTERNAL goalie/lineup data source enters the stack (H2 restated 2026-09-26). The bar does not "
      "move.", milestone=NHL),
    I("cup-model-suspended", "Cup model track suspended (EFL / CL / UEL market-only)", "R", "limitation", "cups", "L",
      "CUP FIX-V2 RE-EXAM: FAIL — CUP MODEL TRACK SUSPENDED",
      "The fix-v2 re-exam FAILED (14.76pp): a rotation information floor. The exam harness + fix-v2 machinery stay "
      "merged.", reopening="A rotation-aware candidate on as-of lineup data (the R-track, winter), passing the frozen "
      "exam.", milestone=CUP),
    I("unl-market-only", "UNL market-only (likely permanently)", "model", "limitation", "unl", "S", "UNL WIRED 2026-09-24",
      "Nations League runs market-only.", reopening="Accepted limit (likely permanent)."),
    # ---- this PR's own operator step ----
    I("ledger-setup", "Ledger setup: project token, bootstrap run, the six saved views", "ops", "operator-action", "all",
      "S", "ISSUES LEDGER + PROJECT BOARD", ref="SELF",
      summary="Add the LEDGER_PROJECT_TOKEN secret (a classic PAT with the `project` scope, or a fine-grained token "
      "with Projects read/write), run the `ledger` workflow's bootstrap, then create the six saved views from "
      "docs/LEDGER.md (the API cannot create views).", flags=["needs-operator"], milestone=CUT),
]


def locate(heading, ref, anchor=None):
    rev = subprocess.run(["git", "log", "--reverse", "--format=%H", "-S", anchor or heading, ref, "--", "BACKLOG.md"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert rev, f"heading not found in history: {heading!r} @ {ref}"
    sha = rev[0]
    text = subprocess.run(["git", "show", f"{sha}:BACKLOG.md"], capture_output=True, text=True, check=True).stdout
    for n, line in enumerate(text.splitlines(), 1):
        if heading in line:
            return sha, n
    raise AssertionError(heading)


if __name__ == "__main__":
    import sys
    self_sha = sys.argv[1] if len(sys.argv) > 1 else None
    out = []
    for it in ITEMS:
        ref = self_sha if it["ref"] == "SELF" else it["ref"]
        if ref is None:
            raise SystemExit("pass the ledger PR's BACKLOG commit for SELF items")
        sha, line = locate(it["heading"], ref, it.get("anchor"))
        it = {k: v for k, v in it.items() if k not in ("ref", "anchor")}
        it["backlog"] = {"commit": sha, "line": line, "heading": it.pop("heading")}
        out.append(it)
    json.dump({"generated_by": "a one-time script; every link resolved from git (law 1)", "items": out},
              open(".github/ledger/backfill.json", "w"), indent=1, ensure_ascii=False)
    print(len(out), "items")
