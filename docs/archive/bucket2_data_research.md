# Bucket 2 — Data-Sourcing Research (2026-06-29)

Research only. Nothing here is committed. The point is to know, per data point,
**what feed it needs, whether we already have access, and how big the build is**,
so we can pick deliberately — ideally after the CLV review tells us the edge
thesis is even worth enriching.

Key finding up front: **most of Bucket 2 needs no new vendor.** The MLB Stats API
we already use (free, trusted) exposes umpires, confirmed lineups, officials, and
the game logs needed to *derive* bullpen usage. The genuinely new-vendor items are
the narrow ones (catcher framing / OAA, umpire run-tendency history).

Tractability scale: 🟢 easy (existing feed, modest code) · 🟡 medium (existing
feed but real new pipeline) · 🔴 hard (new vendor / scraping / licensing).

---

## 1. Weather & roof status — 🟢 EASY (top pick if we add anything)
- **Feed:** Open-Meteo. **Already wired.** No new vendor.
- **What's needed:** map each venue to lat/long (one static table, ~30 parks),
  call the existing Open-Meteo client for first-pitch time, pull wind
  speed/direction, temp, humidity, precip. Roof status (open/closed) is the
  gap — Open-Meteo can't tell us if a retractable roof is shut. Roof state for
  the ~7 retractable-roof parks would need either a manual default (assume
  closed for domes) or scraping a gameday source.
- **Predictive value:** real and well-established for totals (wind out = more
  runs, cold/heavy air = fewer). This is the cleanest cost/value ratio.
- **Build size:** small. Venue→coords table + a totals-context field on the card.
- **Verdict:** if we add ONE Bucket 2 item, this is it. Pipe exists, value is real.

## 2. Umpire assignment + run tendency — 🟡 MEDIUM (assignment) / 🔴 HARD (tendency)
- **Assignment feed:** MLB Stats API, ALREADY ACCESSIBLE:
  `/api/v1/jobs?jobType=UMP&sportId=1&date=YYYY-MM-DD` gives the plate umpire
  per game. Also in game `/boxscore` under `officials`. **No new vendor for the
  assignment itself.** 🟢
- **The hard part:** the *assignment* is free, but the predictive signal is the
  umpire's historical strike-zone / run-environment tendency, which MLB doesn't
  publish as a stat. That requires either (a) building our own per-ump
  run/K/BB history from years of play-by-play, or (b) a third-party source
  (UmpScorecards-style). So: knowing WHO is calling the game = easy; knowing
  what that umpire DOES to run environment = its own modeling project. 🔴
- **Predictive value:** modest, real for totals as a tiebreaker. Not a core
  driver — explicitly a routing tiebreaker per the betting model itself.
- **Verdict:** defer. Assignment is cheap to grab but useless without the
  tendency layer, and the tendency layer is a project of its own.

## 3. Bullpen availability (vs just ERA) — 🟡 MEDIUM (derivable, no new vendor)
- **No clean single endpoint exists.** Confirmed in research. But it's
  **derivable** from data we can already pull: the MLB Stats API game
  `/boxscore` + `/playByPlay` per game gives which relievers pitched and how
  many pitches. Rolling that over the last 3 days per team yields: who pitched
  yesterday, who's on back-to-back, pitch counts last 3 days, likely-unavailable
  arms.
- **Cost:** this is a real new pipeline — a nightly job that pulls each team's
  recent game logs, attributes reliever appearances + pitch counts, and writes a
  per-team availability table. Not a single new feed call; it's an aggregation
  layer. Medium build, ongoing maintenance.
- **Shortcut option (🔴 in spirit):** scrape RotoWire / InsideThePen daily
  bullpen-usage pages. Faster to stand up but fragile (HTML scraping, ToS
  questions, breaks when they redesign). I'd avoid scraping for something we can
  derive from an API we already trust.
- **Predictive value:** genuinely high — a good-ERA bullpen that's gassed is a
  real edge the current model misses. Probably the most valuable Bucket 2 item
  *if* the edge thesis survives CLV.
- **Verdict:** strongest "real signal" candidate, but it's a build, not a
  bolt-on. Park until CLV proves enrichment is worth it; then this is #2 after
  weather.

## 4. Starter workload / pitch-count / leash — 🟡 MEDIUM (derivable)
- **Feed:** same as bullpen — derive from MLB Stats API game logs (recent pitch
  counts per starter, days rest, IP trend). Probable pitchers you ALREADY sync;
  this adds the workload history for each.
- **Cost:** medium, same shape as bullpen availability (an aggregation job over
  game logs). Could share a pipeline with #3.
- **Predictive value:** moderate, mainly for totals + when to prefer F5 over
  full game. The betting model wants it for "short leash → avoid full-game
  unders" routing.
- **Verdict:** pairs naturally with #3 (same data source, same job). If we build
  bullpen availability, starter workload is a cheap add to the same pipeline.

## 5. Lineup confirmation quality — 🟢 EASY-ish (existing feed)
- **Feed:** MLB Stats API `/boxscore` and schedule hydrate gives confirmed
  lineups once posted (~3-4h pre-game), vs projected. We can flag
  confirmed-vs-projected and detect star rest-days (a regular missing from the
  posted lineup).
- **Cost:** small-to-medium. The data's in an API we use; the work is timing
  (lineups post late) and a comparison against expected regulars.
- **Predictive value:** moderate, biggest on getaway days / day-after-night when
  regulars sit. Helps avoid betting a side whose lineup just got gutted.
- **Verdict:** tractable and uses existing access. Reasonable second-tier pick,
  though the late-posting timing makes it operationally fiddly for a morning
  card.

## 6. Defensive OAA / catcher framing — 🔴 HARD (new vendor)
- **Feed:** NOT in the basic MLB Stats API as a clean metric. OAA and framing
  are Statcast-derived; sourcing means Baseball Savant scraping/exports or a
  paid vendor. Real new dependency.
- **Predictive value:** small, situational (fragile low-total unders). Lowest
  value-per-effort in the list.
- **Verdict:** defer indefinitely unless something specific demands it.

## 7. Travel / getaway / doubleheader fatigue — 🟢 EASY (derivable, low value)
- **Feed:** fully derivable from the schedule we already have (prior game
  location + time → travel, day-after-night, doubleheader bullpen drain).
- **Cost:** small.
- **Predictive value:** small — the betting model itself says "minor context,
  small weight only."
- **Verdict:** cheap but low-value; only worth it as a freebie alongside a bigger
  build, not on its own.

---

## Summary ranking (value-per-effort, assuming CLV later justifies enrichment)

| Rank | Item | Tractability | New vendor? | Value | Note |
|------|------|--------------|-------------|-------|------|
| 1 | Weather/roof | 🟢 | No (Open-Meteo wired) | High (totals) | Clear first pick |
| 2 | Bullpen availability | 🟡 | No (derive from Stats API) | High | Real build, real signal |
| 3 | Starter workload | 🟡 | No (same pipeline as #2) | Med | Cheap add to #2 |
| 4 | Lineup confirmation | 🟢 | No (Stats API) | Med | Timing-fiddly |
| 5 | Umpire assignment | 🟡/🔴 | Assignment no, tendency yes | Low-Med | Tendency layer is the cost |
| 6 | Travel/fatigue | 🟢 | No (schedule) | Low | Freebie only |
| 7 | OAA/framing | 🔴 | Yes (Statcast) | Low | Defer indefinitely |

## Recommended sequencing
1. **Do nothing until the CLV review** (~July 8). Enriching an unvalidated card
   is adding precision to possible noise. This is the whole reason Bucket 2 is
   research-not-build right now.
2. **If CLV shows edge:** weather first (pipe exists), then the bullpen+starter
   workload pipeline (one shared job, derived from the Stats API we already
   trust — no new vendor, no scraping).
3. **Hold** umpire-tendency, OAA/framing, lineup-confirmation until a specific
   validated edge asks for them.
4. **Avoid scraping** (RotoWire/ITP) for bullpen — we can derive it from the
   Stats API; scraping trades a clean dependency for a fragile one.
