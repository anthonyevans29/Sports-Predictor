**2026-11-23 — The hourly window page and window_24h.json carry each model row's certification as the registry reads it: each fixture's model block gains "certification" (certified / uncertified / unread), an uncertified row reads "model (uncertified) SIDE PROB (TIER)", a failed read "model (certification not read) ...", a market_only PASS "PASS market-only" (ARCHITECT 2026-11-23 15:52 ET, addendum 473 items 2 and 3; finding #1098; money-path).**
- **Addendum 473 items 2 and 3 (ARCHITECT 2026-11-23 15:52 ET), verbatim:**

  > 2. YOUR Q3, THE LABELLING: THE FINDING IS RIGHT. Read by me in deploy/hosting/sp_window_page.py and
  >    src/walters/window.py: the hourly window page prints an NFL row as the model's side, probability,
  >    tier, the reference, the edge and "PASS", with no word that v1 is uncertified and none that the
  >    PASS is market-only; window_24h.json carries pass_kind market_only and no certification. 214 item
  >    4(a) ruled, verbatim: "the model's probabilities, divergence and quarantine fields stay on the page
  >    labelled uncertified". The export, the bulletins, the coverage map and the Cockpit carry the label.
  >    THE WINDOW PAGE AND ITS FILE DO NOT. No call is made from it and nothing was placed on it, but it
  >    is live and it is not as ruled. DEV 1: A FINDING, ITS ISSUE TODAY (track:ops, class:finding,
  >    sport:nfl, size:S).
  >
  > 3. DEV 1 — THE FIX, one small PR, money-path (a deploy script and the file the reader takes),
  >    read alone:
  >    (a) THE LABEL IS READ, NEVER WRITTEN BY HAND: the certification as the registry reads it for the
  >        row's family and model version, the way closing.nfl_certification does. A read that fails
  >        prints "certification not read" and never blocks the page (law 4).
  >    (b) window_24h.json: each fixture's model block gains "certification". Additive; no field moves.
  >    (c) THE PHONE ROW, when the certification is not "certified": the model part reads "model
  >        (uncertified) SIDE PROB (TIER)", those three as today. When pass_kind is market_only the call reads "PASS
  >        market-only".
  >    (d) TESTS: an NFL row cannot render without the label while the registry reads v1 uncertified; a
  >        row of a certified family renders byte for byte as today (MLB and the PL, from fixtures of
  >        their real shapes); the file's new field; the failed read.
  >    (e) A reviewable head by Tuesday 2026-11-24 12:00 ET. It rides v1.6.11 if it is merged before the
  >        fold opens at 17:00 ET; the fold does not wait for it, and a later patch tag takes it if not.
  >    (f) First enumerate (law 1): every other page or file that shows a v1 figure, from the #780 read's
  >        table A1, each marked labelled or not on the Issue. The read found row 12 alone; say whether
  >        you find the same. Row 14, the web view by match id, is on the loopback only; mark it and
  >        leave it.
