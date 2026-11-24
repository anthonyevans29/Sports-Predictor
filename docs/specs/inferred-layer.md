# The inferred data layer and the host-only store — the design

**Status: DESIGN ONLY. Nothing is built behind this document.** This is lane `inferred-layer`'s step "the design PR, nothing built behind it", owner code, due 2026-12-01 (docs/roadmap.json; Issue #992). The architect's ruling on the design, with the pilot's gate written, is due 2026-12-03. No code, store, timer, key, prompt, folder or row exists for anything below. No bar moves.

It is the proposal Dev 2 posted on #992 on 2026-11-14 (issuecomment-6877950027), done-marked by addendum 385 item 3(c) as "the design proposal to the architect". It is written as addenda 375 and 376 declared the layer (addendum 496 item 4(d)). Each fact it cites about the repository is re-read on main `822ff041`, and §13 lists what changed since the proposal.

The rulings are quoted word for word below and govern this document. Where a later addendum changed an earlier one, the later text governs (addendum 501 item 2). Nothing here is ruled by this document. Every choice it makes is a proposal for the ruling of 2026-12-03. §12 lists the points that most need it; every other choice in the body stands only if that ruling leaves it standing.

---

## 0. The rulings this design is written under

### 0.1 The layer: addendum 375 (2026-11-13 16:40 ET), items 1 and 2, verbatim (recorded on #992)

> 1. THE OPERATOR'S DECISIONS (2026-11-13). He read a vendor survey (the two quotations are my own read of the two pages today; no provider sells a pregame-stamped revision history; SportsDataIO's own guide: "We do not retain prior versions, correction logs, or point-in-time snapshots, and there is no as-of-time query"; Sportradar's terms of 2026-11-12 bar use "for any prediction market, trading platform, financial product or similar offering without Company's prior written consent") and proposed, in his words: "we need to create a prediction layer for these data points ... an LLM-based layer that may even be scanning sports news on a daily basis to infer these additional enriched data elements ... we could always create a secondary lane for predicted inputs for analysis"; then: "We should be layering this as an inferred layer that not only targets our specific missing data, but any additional data points. But it does need to be tagged as separate because it's not written in stone and validated by an API"; and on my strategy page with its six recommendations: "it looks good. I wanted a solid data-driven foundation and this is where we're at". I record the six as adopted: (i) the strategy, starting with ONE pilot, NHL starting goalies, shadow only; (ii) inferred rows live in their own store ON THE HOST, never in sports.db (the laptop pulls its backups), never on the laptop, the public repo or an Issue; (iii) the LLM provider sits behind a plug, with a daily spend cap whose value lives in host.env under a NAME (the provider and the figure are his later decision on the design's cost estimate; no key is bought or installed on this addendum); (iv) inferred context reaches a bulletin only after the pilot's first scored read; (v) after the pilot: NBA, NFL, soccer leagues, MLB and tennis at their 2027 seasons, college last; (vi) THE TWO SOURCING STEPS DUE TODAY: NHL — none bought; we build and measure our own. NFL — his 11-06 decision stands (nflverse depth charts; no feed bought).

> 2. THE LAYER'S RULES, standing from today (the page he approved, in my words here; quote these in the records). (a) TWO TIERS, NEVER ONE TABLE: tier api is a fact a provider or league endpoint serves; tier inferred is a stamped claim derived from public news, with a confidence. Every row carries its tier. An inferred row never overwrites or fills an API field; where an API fact exists for the same question the API fact is used and the inferred row stays as the record to be scored. (b) STATUS WORDS of the inferred tier: projected (our estimate under a declared rule, no source), likely (a source suggests it), stated (a source says it outright); each row with its evidence links, the publication time each source showed, the fetch time, the model and prompt version. Append-only: a change of mind is a new row. (c) TWO CLASSES: a TRACKED ELEMENT has a truth that arrives later and is scored on every row; a CONTEXT NOTE is anything else, never scored, never a model input, labelled as reading. A note becomes an element only by promotion from a candidate register (its definition, the truth that scores it, its free baseline), reviewed by me monthly and approved by the operator. (d) SCORED AND GATED: by element, by status, by lead time, with calibration, against the best free baseline (the API layer's own listing where one exists; "the same as last game"). The sample and the margin are written before the first row is stored and do not move. An element that passes may be DECLARED as an input to a candidate, which then runs at that sport's UNCHANGED gate. (e) FORWARD-ONLY: no season is backfilled by an LLM. (f) NO MARKET CONTENT in what the reader is given: no odds, lines or betting articles (the market is a reference, never a model feature). (g) UNKNOWN STAYS UNKNOWN: no evidence, no row. (h) STORED, NEVER REGENERATED: a new model or prompt version starts a new scored series. (i) EACH SOURCE'S TERMS ARE READ BEFORE ITS FIRST FETCH, by a terms phase as the NBA probe has; facts kept, text not republished; one fetch per page per run; on an objection the source is unplugged and its rows destroyed. (j) EVERY PART IS A PLUG. (k) PASS STAYS PASS: nothing inferred changes a call or a stake before its gates.

### 0.2 The provider and the controlled tests: addendum 376 (2026-11-13 16:45 ET), items 1 and 2, verbatim (recorded on #992; they amend 375 item 1(iii) and item 4(b))

> 1. THE OPERATOR'S TWO DECISIONS (2026-11-13, after 375). (a) THE PROVIDER: "I have a Claude API Key" — the layer's first provider plug is the Claude API. The key's NAME is ANTHROPIC_API_KEY; its value goes into host.env by the operator's own hand at the install, and is never in chat, a terminal block, the repo, a test, a log line or a receipt. (b) THE COST: "we'll run some tests of the prompts and the inputs/outputs without a cap to begin with and then we'll limit it after we've run a few controlled tests to establish cost". So 375 item 1(iii) reads: no spend cap during the controlled tests; the daily cap is set by the operator after them, on their measured cost, and is in force before anything runs on a timer.

> 2. WHAT "CONTROLLED" MEANS, mine to rule and ruled: (a) a test is run BY HAND, by my block, on the host; never by a timer or a chain. (b) Each run is bounded by COUNT, not by money: a fixed number of provider calls and a fixed number of fetched pages, both arguments the run prints first and stops at, so a loop cannot run on unattended. This is a stop on a fault, not a spend cap. (c) Every run prints, per call and in total, the input and output token counts as the provider reports them and the model's name; the cost is worked from those by the operator and me, and no dollar figure is written to the repo, an Issue or a PR. (d) Test rows are TEST rows: they never enter the scored record, and the pilot's scored series starts only at its declared start, with its gate written before its first row (375 item 2(d)). (e) Every other rule of 375 item 2 binds the tests as it binds the pilot: each source's terms read before its first fetch, no market content in what the reader is given, host only, nothing regenerated.

### 0.3 The four texts the design is asked against: addendum 501 (2026-11-24 11:03 ET) supplies them, verbatim from the architect's files

These were relayed by hand before the channel existed. Addendum 501 (#1092, comment 7137047375) put them on the record; they are cited from there.

ARCHITECT 2026-11-13 10:45 ET, addendum 368, item 3, verbatim:
> 3. THE CONDITIONS, standing for this source: (a) ONE MACHINE, THE HOST. Nothing of a report — the
> document, a parsed row, a player's name, a status — is ever on the laptop, the public repo, the exports
> mirror, a bulletin, the Cockpit, an Issue or a PR; tests hold synthetic shapes only. The laptop pulls
> the host's database backups nightly, so THE REPORT'S ROWS DO NOT LIVE IN sports.db. (b) NO NBA
> STATISTICS from nba.com, ever, for anything: (iv) and (vii) plainly reach our use of those. (c) One
> fetch per published report, the plain User-Agent, no crawl. (d) On any objection, block, or change in
> the terms: the timer stops the same day and everything obtained is destroyed — so the store must be
> destroyable whole without touching any other source's append-only rows. (e) The terms phase is re-run
> before the feed is enabled and at each season's start; a changed date line comes to me before the next
> fetch.

ARCHITECT 2026-11-13 10:45 ET, addendum 368, item 5, verbatim:
> 5. THE FEED, AFTER THE REPORT CONSOLE — your proposal in five to ten lines, no code, under these four
> constraints: (i) THE SOURCE IS A PLUG. One small interface (fetch, then rows of kind `injury_status`
> with the source's own stamp), the official report its first implementation, a vendor's feed a second.
> Nothing downstream — the graph, a page, any future model input — names a source; it reads the kind. A
> swap is one timer enabled and another disabled, by my block; both may run side by side for a comparison
> window. (ii) A HOST-ONLY STORE for this source: the record's two-table shape and its append-only
> discipline, in its own SQLite file on the host that no backup pull, mirror push or export carries off
> the machine. Say where it lives, how it is backed up on the host itself, how the graph projection and
> coverage read it, and what sp_deploy, T11 and THE HELD LIST need to know of it. (iii) THE DESTROY PATH:
> one command, run by my block alone, that removes this source's store and its payloads whole and leaves a
> receipt line saying what was destroyed, when and on whose ruling. (iv) The new source word and store are
> a stored-schema change: say whether that is a migrate file of its own (354 item 2) or the store's own
> init, and how the schema check reads it. I rule on the proposal; the feed PR follows it.

ARCHITECT 2026-11-13 16:40 ET (21:40Z, read from the clock), addendum 375, item 4, verbatim:
> 4. DEV 2 — TWO THINGS, nothing built or run. (a) THE CEILING READINESS READ by 11-19, five to eight
> lines on #105: the question the test will ask is whether KNOWING WHO ACTUALLY STARTED moves an NHL model
> past its bar at all; if it cannot, no projected-starter source, bought or inferred, is worth building
> for hockey. Tell me: what candidate nine's goalie term was to be and what the GSAx feasibility receipt
> established; whether the true starter of every game of 2023-24 to 2025-26 is derivable from what is
> stored, and the coverage by season; whether the harness in src/walters/nhl_backtest.py can run a goalie
> term on a RETIRED cohort with goalie figures taken strictly as of each game's morning; what stability
> guards such a candidate must declare (157 item 3); what is unbuilt; and anything the declaration must
> name that I have not asked. NO FIGURE of any goalie-aware model on any cohort is produced or looked at
> before my declaration. (b) THE FEED PROPOSAL OF 368 GROWS INTO ONE DESIGN: one host-only store, apart
> from sports.db, that holds both the NBA report's rows (tier api, host-only for its terms) and the
> inferred tier of item 2, the tier on every row; each source and the LLM provider a plug with its own
> destroy path; the reader's fixed vocabulary (the availability record's kinds, extended, not replaced);
> the scoring report of item 2(d); the spend cap; a cost estimate per sport per day for the pilot; what
> leaves the host (scores and labelled summaries to the private mirror, nothing else). The proposal comes
> to me as text by 11-25, the design PR by 12-01. YOUR ORDER: the v23 readiness read (11-18) first, as
> dated; the matcher proposal; (a); then (b).

ARCHITECT 2026-11-13 16:45 ET (21:45Z, read from the clock), addendum 376, item 3, verbatim:
> 3. DEV 2 — INTO THE DESIGN (375 item 4(b)): name the Claude API as the first provider behind the plug;
> add a small bench for the controlled tests of item 2 (the prompt and its version as files in the repo,
> the inputs and outputs kept on the host only); give the cost estimate as tokens per game and per day for
> the NHL pilot, in tokens and calls, so the operator can price it. One design question to answer in the
> proposal, not to decide alone: whether the reader fetches a FIXED list of sources itself and hands the
> text to the model (my lean: it keeps 375 item 2(f) and 2(i) checkable), or lets the provider's own web
> search choose pages (it cannot be held to a terms phase or to the no-market-content rule in the same
> way). The dates of 375 stand.

### 0.4 Later rulings that bear on the design

- **The graph's node shape** (addendum 379 item 2, 2026-11-14, verbatim in part, as BACKLOG records it): "THE THREE-TIMES CHOICE (#995) — RULED: (B), AND NOT AS AN EXPERIMENT. THE GRAPH'S SHAPE CHANGES: EACH ASSERTION IS A NODE." BACKLOG records its reason in summary: "An inferred claim needs edges of its own (to its evidence, its successor and its truth), and an edge cannot carry an edge." §9 follows it.
- **The design proposal done-marked** (addendum 385 item 3(c), verbatim as docs/roadmap.json holds it): "lane inferred-layer, \"the design proposal to the architect\", due 11-25, DONE 2026-11-14 by Dev 2's comment on #992 (my ruling on it stays due 12-03)".
- **The landing projection is not a pregame starter signal** (addendum 428 item 5(b), verbatim in part): "the slot we store as projected_starter does not move before the game and named the starter on fewer than half the sides; as it stands it is not a pregame starter signal. It stays stored. The inferred layer's NHL pilot (#992) is designed knowing that, in the ruling due 12-03." §7 takes it into the baselines.
- **The true-starter ceiling: FALSE** (addendum 496, 2026-11-24 09:48 ET, item 4, verbatim):
  > 4. WHAT FOLLOWS, AS WRITTEN BEFORE THE RUN (491 item 6(a)), and nothing more:
  >    (a) I build no as-of estimate and no projected starter of this quantity as an NHL model input.
  >    (b) NHL stays MARKET-ONLY and the model track stays suspended. v7 stays the failed-gate shadow. NHL 2025 stays retired; this was its ninth read and its last.
  >    (c) The reopening condition is no longer a goalie or lineup source. A new NHL candidate needs a new idea in another form, declared by its own addendum on 2026-27 as it accrues (600 games or more), at the unchanged gate.
  >    (d) What the inferred layer's NHL pilot is now for is ruled on 2026-12-03, as 491 said, not today. DEV 2: write the design PR of 12-01 as 375 and 376 declared the layer, and add one paragraph saying what the pilot would measure now that no NHL model input waits on it. Do not choose for me; I rule on 12-03.
  >    (e) Nothing is rerun. Nobody computes a variant of the probe with a constant, a season or a rule changed (491 item 8).

  §7.6 is that paragraph.

---

## 1. The store: host only, one SQLite file per source, never sports.db

The governing texts: 375 item 1(ii), 368 item 3(a), and 368 item 5(ii).

- **Where it lives.** `SP_PRIVATE_DIR` is a NAME in host.env, and the code refuses when it is unset; its value is `/var/lib/sports-predictor/private/`. Each source has one folder, `<source>/`, and everything the source produced lives in it:
  - the store, `store.db`;
  - the payloads, `payloads/<date>/`;
  - the bench files, `bench/` (§6);
  - the receipts of the source's probe phases, `receipts/`.

  Destroying a source is removing one folder (§4). The source name `sports` is reserved and refused, so no private file can ever match the backup pull's pattern (§2).
- **Who makes the folders: the architect's enabling block.**
  - The block makes `SP_PRIVATE_DIR` and `/var/backups/sports-predictor-private/` (owner sp, mode 0700).
  - `install.sh` is not that gate. It runs only in the architect's enabling blocks (addendum 374 item 2; docs/RELEASES.md). When it runs, it copies every unit file and makes its own folders whatever lane is being enabled (`deploy/hosting/install.sh`), so it cannot gate one lane.
  - A source's first `store.db` is made by an explicit `cli.py private-init --source <name>`. That is not a migration (368 item 5(iv); §1.4).
- **Outside every carrier.** The folders are outside the checkout and outside `/var/backups/sports-predictor`. Each carrier is pinned by its own test, so a later change that would carry a private file off the host fails CI:
  - `deploy/hosting/pull_backup.py`: its `REMOTE_DIR` and the daily pattern `^sports_\d{4}-\d{2}-\d{2}(_\d{6})?\.db$`;
  - `deploy/hosting/pull_exports.py`: its `REMOTE_DIR` and its top-level-only listing (`find … -maxdepth 1`). The `--remote-dir` override, which defaults to `SP_HOST_EXPORTS`, is pinned too, so a changed override cannot point it under `SP_PRIVATE_DIR`;
  - `deploy/hosting/exports_mirror.py`: top-level `exports/*.json|*.md`, plus the one kept subtree `bulletins/**` (and §8's second, if ruled);
  - `deploy/hosting/sp_migrate.py pack`: it copies `exports/` RECURSIVELY. It is a laptop-side tool, but nothing refuses it on the host, so a pack would carry `exports/inferred/**` (§8). The design pins it: the pack leaves out `exports/inferred/` and refuses any path under `SP_PRIVATE_DIR`.

### 1.1 Two tiers, never one table (375 item 2(a))

Each tier has its own tables. No table holds both tiers, and every row still carries its `tier` value, checked by the insert guard.
- **Tier api:**
  - `api_observations`: the payload's sha256, the fetch time and the HTTP status;
  - `api_assertions`: the kind, the provider ids, the source's own stamp, and the league's words verbatim in `attrs`.
- **Tier inferred:**
  - `inferred_observations`: one row per text actually handed to a call. Each row holds that text (the page trimmed for one game by the trim rule of §12(d)), its sha256, the page's URL, the raw page's sha256, the trim rule's version and the fetch time. The raw page is fetched once per run and kept once, in the domain's `payloads/` (375 item 2(i): one fetch per page per run), so a page that feeds two games gives one payload and two observations;
  - `inferred_call_inputs`: each call's ordered input manifest. It has one row per observation handed, with the `call_id`, the position, the observation's id and its sha256. It also has one row for the facts handed: the two teams' provider ids and the game's start time, as handed. Together with the prompt file's sha256 and `max_tokens`, it names exactly what a call was handed, in order. So §5's reproduction and audit do not rest on the evidence the answer chose to cite. It lives in the domain's own store, so it goes with the domain (§4);
  - **the write order:** a call's observations and its manifest are committed to the domain's store BEFORE its reservation row (§6) and before the request is sent. A call that crashes after sending still has its full input on record;
  - **the evidence rule:** every evidence link of a claim must resolve to an observation in that call's own manifest, and so to the call's own domain. The writer refuses a claim that cites anything else and counts the refusal by cause, with a test. So a claim can never carry another domain's page past that domain's destroy;
  - `inferred_assertions`, each carrying:
    - `status_word` (projected | likely | stated, 375 item 2(b));
    - `evidence` (each link with the publication time its page showed);
    - the fetch time;
    - the provider and its model name;
    - the prompt file and its sha256;
    - `lineage` (§7.5);
    - `confidence`;
    - the call's `call_id`.
- **The calls ledger, its own source (the P1 of the design's review).** `inferred_calls` lives in its own folder, `<SP_PRIVATE_DIR>/inferred_calls/`. It is append-only like every store, and it holds TIMER calls only: a bench call is recorded in its own bench folder in the same shape, never here (§6; 376 item 2(d)). Each timer call writes two rows, keyed by `call_id`:
  - **the reservation row,** before the request: the element, the games and sides asked, the one domain whose pages it read (§3.2), the provider, its model, the prompt's sha256, the start time and the call's bound (§6);
  - **the settlement row,** after: the end time, the provider's own token counts (input as the sum of `input_tokens`, `cache_creation_input_tokens` and `cache_read_input_tokens`, and `output_tokens`), and the outcome. The outcome is answered, no evidence, refused, or failed.
  - **A call with no settlement row** (a crash) is open. It counts at its bound for its UTC day, and the day's report prints it as open. **A call that ends without a provider usage block** (a timeout, a connection error) settles as failed and keeps its bound as its count, because tokens may have been billed.

  It holds no page text, no page hash and no answer text: the input manifest stays in the domain's store. The daily caps count it (§6), so a call that writes no claim (375 item 2(g)) is still counted. A destroy of a domain leaves its calls' counts here and removes everything the domain supplied (§4). On an objection to the provider, it goes with the provider's destroy (§3.3).
- A source's file holds only its own tier's tables. An api source's file has no inferred tables, and an inferred reader's file has no api tables.
- There is no `test` column. Test rows exist only in the bench files (§6), never in a store (376 item 2(d)).

### 1.2 Kinds are the store's own vocabulary (375 item 4(b): "the availability record's kinds, extended, not replaced")

- A private tuple holds a copy of the record's KINDS (`src/availability/record.py`: `KINDS = AVAILABILITY_KINDS`, which includes `projected_starter`, `eventual_starter` and `injury_status`), plus `context_note` and the inferred kinds (§3).
- `AVAILABILITY_KINDS` and sports.db's `trg_availability_*` triggers are untouched.
- The store has its own trigger set, rendered for its own table names: no update, no delete, and an insert guard on tier, kind and status word.
- It has its own writer, with its own payload-root rule: under `<source>/payloads/` only. The record's `PAYLOAD_ROOT` is `logs/availability/<source>/<date>/` and is not reused.

### 1.3 Linking a row to a game

A row links to a game by provider ids: the league's own ids, and the stored match's `external_ids`. It never links by sports.db's own row ids, which are machine-local.

### 1.4 The schema and its checks (368 item 5(iv))

- **The tables** are SQLAlchemy Core `Table()` objects in their own `MetaData`, in `src/private/schema.py`, with no `__tablename__`. The test that only `src/db/schema.py` assigns `__tablename__` (tests/test_schema_ddl_check.py) holds unchanged.
- **A schema change** ships with a root `migrate_private_<what>.py` (354 item 2). `sp_deploy.py`'s `MIGRATION_NAME` already matches that name. The build that follows this design adds:
  - `sp_deploy`'s schema warning (`SCHEMA_FILE`, today `src/db/schema.py` only) reads `src/private/schema.py` too;
  - `run_migrations` backs up every private store (§2) before a `migrate_private_*` file runs, under the deploy's own lock and, per store, under that source's lock (§4), taken before the store is opened. A store whose lock it cannot take is not migrated, and the deploy reports it. That backup is not sports.db's;
  - `schema_ddl_check.py`'s DUMP compiles both MetaData;
  - CONTRIBUTING's stated limits name the second MetaData. Its sentence "Every table is declared in src/db/schema.py (a test pins it)" becomes false and is rewritten; the test that pins the limits is updated with it.
- **The readiness predicate** is `private.migrated(session, <file>)`, on the pattern of `record.migrated(rs)`, which takes a session.
- **The first private tables and the DDL check.** Once DUMP compiles the private MetaData, CI's rule that a new table ships with its migrate file (CONTRIBUTING, 358 item 2) covers them. So the PR that first adds them ships `migrate_private_0001.py`:
  - it applies the schema to every private store that exists;
  - it creates nothing where none exists, so it is a no-op on a host with no stores.

  `private-init` makes a new store at the current schema and records the migrate files as applied. That is how 368 item 5(iv) is answered: the store's own init makes it, and a migrate file carries each change after.

## 2. Backup on the host itself, never pulled (368 item 5(ii))

- **The daily backup.** Each source's `store.db` gets a daily `.backup` to `/var/backups/sports-predictor-private/<source>_YYYY-MM-DD.db`, mode 0600, with a `.sha256` sidecar.
  - The name can never match the pull's pattern: `sports` is a reserved source name (§1), and the folder is not the pull's `REMOTE_DIR`.
  - `sp_prune.py` touches only `sports_*.db` in its own folder, so the private folder gets its own prune rule. The retention is the architect's to set (§12).
- **T11, a fresh host.** The store is NOT restorable off the host, by design. On a fresh host:
  - the enabling block creates the two folders, and `private-init` creates each source;
  - it needs the NAMES `SP_PRIVATE_DIR`, `ANTHROPIC_API_KEY`, `SP_INFERRED_DAILY_CALLS` and `SP_INFERRED_DAILY_TOKENS`;
  - every lineage starts again (§7.5).

  T11 states this in a paragraph of its own, which the build adds to docs/specs/hosting-h1.md.

## 3. Every part is a plug, each with its own destroy path (375 item 2(j), 375 item 4(b), 368 item 5(i))

### 3.1 The Source plug

- `fetch(plan) -> Observation` and `parse(payload) -> [Assertion]`, with kind `injury_status` for the NBA report and the source's own stamp.
- The first source is the official NBA report, tier api (§11). The plug holds the plain User-Agent, one fetch per published report, and no crawl (368 item 3(c)).
- Nothing downstream names a source; it reads the kind (368 item 5(i)). A swap is one timer enabled and another disabled, by the architect's block, and two sources may run side by side for a comparison window.
- Its destroy is §4, on its folder.

### 3.2 The inferred reader is one source per news domain

- Each listed domain is its own source, with:
  - its own folder;
  - its own terms phase (375 item 2(i));
  - its own pages (`inferred_observations`).
- **One call reads one domain (the proposal, §12(b)).** Each call is handed the pages of ONE domain only, and writes its claims, its input manifest and its pages into that domain's file alone.
  - **Why:** a claim made from several domains' text depends on each of them. A copy kept in domain B of a claim the model made from A's text would outlive A's destroy, which is the exact case the destroy exists for. Removing that copy from B would touch another source's append-only rows, which 368 item 3(d) forbids ("destroyable whole without touching any other source's append-only rows").
  - With one domain per call, every claim depends on one source, and destroying it is removing its folder (§4). No other source's rows are touched.
  - **The cost:** a game read from three domains is three calls and three claims (§10 counts calls per domain). Each domain's claims are their own lineage (§7.5) and are scored and gated on their own (§7.4), so the report also says which domain is worth its calls.
- **One timer per domain.** The reader is a templated unit, `sp-inferred@<domain>.service` with its `.timer`, one instance per domain. Disabling one domain is disabling its instance, so 368 item 3(d)'s "the timer stops the same day" applies to that domain alone (§4).
- **The score's key.** The score counts one claim per (`call_id`, side, element), since one call answers for both sides (§5).

### 3.3 The Provider plug

- `infer(prompt_file, inputs) -> (text, usage)`. `usage` is the provider's own input and output token counts and the model name.
- The first provider is the Claude API (376 item 1(a); 376 item 3). The provider's own web-search and fetch tools stay OFF in every call (§5).
- **The key.** The name `ANTHROPIC_API_KEY` is the one 376 item 1(a) rules. Its value goes into host.env by the operator's own hand at the install, and is never in chat, a terminal block, the repo, a test, a log line or a receipt.
  - The build adds the name to `sp_common.SECRET_ENV`, with a test.
  - `record.py` already redacts any variable whose name ends in `_KEY`, from `os.environ` (`_SECRET_NAME`). The build adds this name to `record._SECRET_ENV`'s explicit list as well.
  - That list today lacks `API_BASKETBALL_KEY`, which `sp_common.SECRET_ENV` has. The build makes the two lists agree, with a test.
- **TWO FACTS for the ruling (§12(h)):**
  - **host.env says keys don't live there.** `deploy/hosting/etc/host.env.example`'s header reads: "API keys do NOT live here: they travel in the checkout's .env (H0-15 manifest) and are read by config.py as on the laptop." 376 item 1(a) rules the key into host.env, so that comment changes with the build.
  - **Eleven units load host.env** (`EnvironmentFile=-/etc/sports-predictor/host.env`), so each would hold the key in its environment. They are sp-availability-observe, sp-backup-prune, sp-backup, sp-boot-receipt, sp-chain@, sp-closing-watch, sp-cup-observe, sp-exports-squash, sp-notify@, sp-soccer-refresh and sp-web.
  - **`UnsetEnvironment` alone does not keep the key from them.** host.env is root:sp mode 0640 (`install.sh`), every unit runs as `User=sp`, and the code reads the file again in-process: `sp_common.setting()` and `load_host_env()`, `sync_hold`'s re-read of `SP_SYNC_HOLD`, and `desk_policy.role_reading()`. A unit with the key unset from its environment could still read it from the file.
  - **Hiding the file from those units breaks the host.** `desk_policy` reads the machine's role from host.env strictly. By addendum 116 item 2, "a host.env that EXISTS but cannot be read makes the role UNKNOWN" (`HOST_FENCE_UNREADABLE_REASON`). An `InaccessiblePaths` line on host.env leaves the path existing and unreadable. So inside sp-chain@ and sp-closing-watch, every host-only command would refuse: the expansion leagues' shadow export at the end of the soccer chains, the PL availability arm, and the other host-only shadows. sp-web would also stop honouring an `SP_SYNC_HOLD` set after it started, because `sync_hold` would silently read nothing. The graph unit's `InaccessiblePaths=/etc/sports-predictor` shows only the mechanism: that unit loads no host.env and runs no host-only command.
  - **So no option keeps the value in host.env, keeps it from the other units, and leaves 116 item 2 as it stands.** The three options, for the ruling (§12(h)):
    - **(A) The proposal: as ruled, with the exposure every key has today.** The value lives in host.env (376 item 1(a)). Each of the other eleven units carries `UnsetEnvironment=ANTHROPIC_API_KEY`, so no other unit's environment holds the key and no child process inherits it, pinned by a test. Any sp process can still read the file, as every sp unit today can read the checkout's .env, where every other provider key lives (host.env.example's header; the graph unit's header). This adds no exposure the other keys do not already have.
    - **(B) Hide host.env from the units that run no role-reading or hold-reading path.** The build would list them unit by unit, with a test. sp-chain@, sp-closing-watch and sp-web cannot be on that list, so the key stays readable where most code runs. This adds lines without closing much.
    - **(C) A root-only second file passed to the reader's instances alone,** for example by systemd's `LoadCredential=`. That closes the exposure, but it moves the value out of host.env and departs from 376 item 1(a). So it is set out only as the architect's to rule, never proposed as within the ruling.
  - **What every option leaves open:** a process run by hand as `sp` can read whatever sp can. That is the operator's own hand on the host.
- **The plug's request settings, pinned by test:** `max_retries=0`, so one reservation covers exactly one billed attempt (§6), and no `cache_control`, so the settled input is the plain input (§1.1 counts all three input fields all the same).
- **The provider's destroy path.** What the provider holds is our calls' inputs and outputs; our own copies are the store's rows and payloads, which go by §4, per source. On an objection to the provider:
  - every `sp-inferred@` timer stops;
  - the block disables the provider plug;
  - every inferred source made through that provider, and the calls ledger, is destroyed by §4.

  The provider's own retention is a matter of its terms. The terms phase reads them and keeps the facts (375 item 2(i)), and the provider plug's PR quotes those facts. None is quoted here, because none has been read yet.

### 3.4 Kind plus tier, and the precedence rule (375 item 2(a))

- An inferred claim never uses an api kind. The goalie claim's kind is `inferred_starter`, never `projected_starter`.
- Every reader (the graph, a page, any future input) selects by kind AND tier. Where an api fact exists for the same question (the same game, side and element), the api fact is used, and the inferred row is not read as a fact. The inferred row stays as the record to be scored. A test pins this on the graph's projection.

### 3.5 The timers

- Each plug's timer PR adds it to:
  - T11's `TIMERS_BY_BLOCK` line;
  - the Schedule table;
  - THE HELD LIST table, with its addendum and lift condition;
  - the recipe's `HELD=` line.
- What is tied by test today:
  - THE HELD LIST's table and its `HELD=` line (tests/test_hold_search_recipe.py);
  - the T11 lists, the shipped timers and the Schedule rows (tests/test_hosting_pack.py).
- `TIMERS_BY_BLOCK` and THE HELD LIST are two lists by 356 item 2, and no test ties one to the other. The design does not tie them.
- THE HELD LIST holds two entries today: tennis and ncaamb (404 item 1).

## 4. The destroy path (368 item 3(d); 368 item 5(iii)): `cli.py private-destroy --source <name> --ruling "<addendum N item M>"`

- **Who runs it.** It runs on the host only (`desk_policy.not_host_reason`), and the architect's block alone runs it. It refuses without a ruling string, and while the source's timer is still enabled.
- **No writer runs while it removes.** A disabled timer does not stop a service that has already started, and that service could recreate the folder or write a payload after the removal. So:
  - **the lock:** any process that writes under `<source>/`, or writes a private backup of it, holds the source's lock, `<SP_PRIVATE_DIR>/.locks/<source>.lock` (an exclusive `flock`), for its whole run. That means its timer's service, the bench, `private-init`, the daily private backup, `run_migrations`' backup and migrate (§1.4), and the NBA probe's report phase if its receipts move there (§12(l)). The lock sits outside the source's folder, so it outlives the removal;
  - **a reader holds two locks:** an `sp-inferred@` run and the bench take their domain's lock and then the ledger's (`inferred_calls`), always in that order;
  - **writers take the lock non-blocking and refuse if it is held.** Once holding it, every writer but `private-init` refuses if `<source>/` or a migrated `store.db` is absent. None of them ever creates the folder. A writer that waited could otherwise recreate the source after its destroy;
  - **the order:** the destroy refuses while the source's timer is enabled or its service is active (`systemctl is-active`). For an inferred domain, that is its `sp-inferred@<domain>` instance. For the ledger, it refuses while ANY `sp-inferred@` timer is enabled or service is active. It also refuses while `sp-availability-graph.service` is active. It then takes the source's lock non-blocking and refuses if it cannot. It holds the lock through the removal, the graph step and the receipt line;
  - **the graph's own lock:** the graph unit cannot see `<SP_PRIVATE_DIR>` (§9), so the rebuild takes a second lock it can reach, `logs/availability/graph/.rebuild.lock`. The destroy takes that one non-blocking too, after the source's, and holds it through the graph step. A rebuild that opened the old backups therefore cannot write its file after the destroy;
  - **the check:** after the removal, still holding both locks, it checks three things: the folder is gone, no `<source>_*.db`, `.sha256` or `.partial` is left in `/var/backups/sports-predictor-private/`, and the graph file is absent. If any check fails, it refuses (exit 2) and writes no receipt;
  - **what is left behind:** the two lock files. They hold no row and no text.
- **What it prints first, before it removes anything:**
  - the store's rows by table, and its sha256;
  - the payload count and bytes;
  - the bench files;
  - the receipts;
  - the private backups.
- **What it removes:** the source's folder (`<source>/`: the store, the payloads, the bench and the receipts), and its private backups.
- **Then the graph.** It removes the graph file. It never rebuilds in-process: the rebuild runs only in its own unit (347 item 5(b)), and the next run, which the block may start at once, rebuilds without the source. The graph's copy of the rows does not wait for the night.
- **The receipt line** (368 item 5(iii): "a receipt line saying what was destroyed, when and on whose ruling"). It appends one record through `sp_common.append_receipt`: `{"kind": "private-destroy", "source", "rows", "payloads", "bench", "receipts", "backups", "graph", "ruling"}`. The `·` line is the console only.
- **The NBA probe's receipts.**
  - Today the probe's report phase REQUIRES `--out` under the checkout's own resolved `logs/availability/` (`refuse_report_out` in scripts/nba_injury_report_probe.py, which enforces 368 item 4(ii)); `--out` has no default.
  - **A proposal against a ruled rule (§12(l)):** the report phase would write under `<source>/receipts/` instead. 368 item 4(ii) rules the location, so this moves only on the architect's ruling.
  - Until such a move, the destroy removes no file under `logs/availability/` on its own judgement. That tree also holds every record source's append-only payloads and the graph's folder. It removes only the paths the block names with `--also <path>`. Each must be a regular file under `logs/availability/` that is in no record source's payload folder (`logs/availability/<source>/<date>/`) and not in the graph's folder, and each is printed before it goes.
- Nothing else is touched.

## 5. The inferred reader, and 376 item 3's question

- **376 item 3's question, answered: a FIXED list of domains that the reader fetches itself.** I agree with the architect's lean, for four reasons:
  - each domain gets a terms phase before its first fetch (375 item 2(i));
  - the exact text handed to the model is stored, so every call can be reproduced and audited;
  - a market-content check refuses any page before the call (375 item 2(f)). It uses a fixed word list, given as data in §12(d), and each refusal is counted;
  - one fetch per page per run holds by construction.
- **Why not the provider's own web search:** it chooses its own pages, so none of the four can be checked. No domain is named in this document. Each is named in the reader's PR, with its terms phase, for the architect's ruling.
- **The inputs for one game:**
  - one listed domain's pages' text for both teams (one domain per call, §3.2), trimmed to the paragraphs that name a goalie or the game (the trim rule is in §12(d));
  - the two teams and the start time.
- **The landing projection is NOT given to the model.** It is a baseline (§7), and giving it to the model would make the score circular.
- **The answer.** The fixed prompt asks for one JSON answer per side: the goalie, the status word, the evidence links with their shown times, and the confidence.
- **No evidence, no row** (375 item 2(g)).
- **Forward only** (375 item 2(e)). The bench and the timer both refuse any game whose start has passed. The timer also refuses any game before its lineage's declared start, which is written in the register with the gate (§7.4; 376 item 2(d): "the pilot's scored series starts only at its declared start"). The bench's rows are test rows in no lineage (§6), so only the first rule binds it. Nothing is backfilled.
- **Context notes** (375 item 2(c)). A context note is kind `context_note`, labelled "reading". It is never scored and never a model input; every model input refuses the kind, by test.
  - A note becomes a tracked element only by promotion from the CANDIDATE REGISTER, `docs/inferred/register.json`. Each entry holds the note's definition, the truth that scores it, and its free baseline.
  - The architect reviews the register monthly and the operator approves it (375 item 2(c)). The PR that promotes a note carries both.

## 6. The bench for the controlled tests (376 item 2; 376 item 3)

- **The command:** `cli.py inferred-bench --provider claude --source <domain> --prompt prompts/nhl_goalie/v1.md --games <ids…> --max-calls N --max-pages M`. One domain per run (§3.2).
  - It runs on the host only, by hand, by the architect's block (376 item 2(a)). It refuses under systemd (an `INVOCATION_ID` check) and is never on a chain or a timer.
- **What it prints.** First the two bounds, at which it stops (376 item 2(b)). Then, per call and in total, the input and output tokens and the model name (376 item 2(c)). No dollar figure is printed or written.
- **Where its output goes:**
  - its inputs, outputs and rows go to `<source>/bench/<ts>/` under the private folder, with each call's record and input manifest in the ledger's and manifest's own shapes. The scoring report never reads them, and §4 destroys them with the source (376 item 2(d));
  - its calls write no row to the calls ledger, so they never count against the timer's daily cap.
  - the prompts are files in the repo, each with its version and sha256 (376 item 3).
- **The caps.** No spend cap applies during the controlled tests (376 item 1(b)). Before any timer runs, the daily cap is set by the operator on the measured cost (376 item 1(b)), which the operator and the architect work out from the bench's token counts (376 item 2(c)).
  - **Its unit is a proposal:** 375 item 1(iii) rules "a daily spend cap", and this design holds it as two NAMES in host.env, `SP_INFERRED_DAILY_CALLS` and `SP_INFERRED_DAILY_TOKENS`, in calls and tokens rather than money. No dollar figure is written anywhere (376 item 2(c)). That unit is the architect's to rule (§12(e)).
  - The timer refuses if either is unset.
  - It stops at either cap, counted from the calls ledger (§1.1) for the UTC day, one count per call whatever its outcome.
  - **A timer call is reserved before it is sent, so the last call of a day cannot run past the cap.** The reservation and the cap check run in the timer's path only. The bench stops at `--max-calls` and `--max-pages` alone, which is a stop on a fault and not a spend cap (376 item 2(b)).
    - Each call sets a fixed output bound, `max_tokens`, from the prompt file.
    - **The input bound is a working bound, not a property of the tokenizer.** It is the UTF-8 byte length of the whole serialised request body (the system text, the messages and any output schema), plus a fixed per-call overhead that the prompt file names. The bench measures how far the provider's reported input stays under it, and the prompt's PR prints that margin.
    - The reservation row (§1.1) carries the input bound plus `max_tokens` as the call's bound.
    - The call is refused unless the day's settled tokens, plus every open call at its bound, plus this bound, stays within `SP_INFERRED_DAILY_TOKENS`. The calls cap counts open calls the same way.
    - The settlement row (§1.1) replaces the bound with the provider's own counts. A call that has none keeps its bound.

## 7. Scored and gated (375 item 2(d)): `cli.py inferred-score --element nhl_starting_goalie --sports-copy <a sports .backup copy> --private-backup-dir <the private backups' folder>`

Every copy opens mode=ro + immutable=1 (198 item 6(ii)). The score reads every inferred domain's backup of the same day, as the graph does (§9), because each domain's claims are in its own file (§3.2). It counts each (`call_id`, side, element) once, and reports by domain as well as in total.

### 7.1 The truth

The truth is in sports.db, from two stored readings:
- **The landing watch's `eventual_starter`** (`src/availability/nhl_landing.py`). It writes one row per goalie with time on ice above zero, per side, and marks `two_in_net` when a side has two or more. A normal game has one row a side; a side with a relief appearance has two.
- **The boxscore's own starter flag**, `is_starter` in `nhl_goalie_appearances` (`src/ingestion/nhl_goalies.py`). It is a sports.db column, not an attribute of the assertion.

The proposal for a side's truth (part of §12(f)):
- the one goalie whose `is_starter` is TRUE, where exactly one is;
- otherwise the side's single `eventual_starter` row, where there is exactly one;
- otherwise no truth, and the side is left out by cause and counted (law 4).

A claim that names a reliever is never counted correct.

**The answer's goalie and the truth's goalie are matched by NHL player id, never by name (part of §12(f)).** The model names a goalie in words, while both truths carry the NHL `playerId`, in two different places:
- the `is_starter` truth, as `nhl_goalie_appearances.goalie_id` (an integer);
- the `eventual_starter` truth, as `availability_assertions.source_player_id` (the playerId as text; that row's `player_id` is NULL by design, `nhl_landing.py`). The resolver's integer is compared with `int(source_player_id)`, and a value that does not parse leaves the side unscored by cause.

So each claim's name is resolved to an id by one fixed rule before it is scored:
- **The team:** the side's `team_abbrev`, taken from the claimed game's own appearance row for that side (by `nhl_game_id` or `match_id`, plus side). Where that row is missing or its `team_abbrev` is NULL, the claim is unscored under its own counted cause (law 4).
- **The season:** `nhl_goalies.season_label(game_start)`, applied to the claimed game's start and to each appearance row's `game_start` alike. It is never read from `matches.season`, which is int-style and would match nothing.
- **The pool:** the goalies stored in `nhl_goalie_appearances` with that `team_abbrev` in that season, in games that started before the claim was made. Rows with a NULL `team_abbrev` are left out. The resolver reads them from the sports copy.
- **The normalisation:** Unicode NFKD, accents stripped, case-folded, every character that is not a letter turned into one space, and spaces collapsed. It is applied to the answer's name and to each stored `goalie_name` alike.
- **The match:** exact equality after normalisation, against the pool.
  - Exactly one goalie matches: the claim carries that id.
  - None matches, or more than one: the claim is unscored and counted by cause ("not in the pool" or "ambiguous"). There is no fuzzy match, no initials rule and no guess (law 4).
- **A known cost:** a goalie with no stored game for this team this season is never in the pool: a debut, a recall, a trade or waiver arrival whose games were all for another club, or a backup not yet used. Early in a season that is common. A claim naming him is counted "not in the pool", and the report prints that count by cause beside the score.
- The resolver's id, its rule's version and the cause are stored with the score's rows, never written back to the claim.

### 7.2 The two free baselines, as they stand

- **"The same as the side's last game":** available at every lead time.
- **The API layer's own listing, the landing page's projected starter, where the watch stored one.**
  - The watch polls only from T-120: its pregame labels are T-120, T-90, T-60, T-45, T-35, T-30, T-15 and T-0 (nhl_landing.py). So a read made earlier than T-120 has no stored API baseline, and only "the same as last game" applies to it.
  - Addendum 428 item 5(b) read this listing as "not a pregame starter signal": it "does not move before the game and named the starter on fewer than half the sides". It stays a baseline because 375 item 2(d) names "the API layer's own listing where one exists". It is a weak one, and the report says so beside it.

### 7.3 What the report gives

The report gives, by status word, by lead time and by day:
- the share of claims whose named goalie matches the truth;
- the calibration of the stated confidence, in bands;
- the same share for each baseline that exists at that lead time;
- coverage counts, by source and day.

The lead times are the reads the reader makes (§10: a morning read at T-8h and a late read at T-90). The proposal of 11-14 listed four buckets (T-12h, T-6h, T-90 and T-30), which two reads a game could never fill. The buckets, and the confidence bands, are written with the gate (§12(k)).

### 7.4 The fixed point and the gate

- **The sample and the margin are written before the first row.** They go in `docs/inferred/register.json` before the store accepts its first inferred row (375 item 2(d)). `private-init` and the writer refuse an element with no written sample and margin, and the values do not move. They are the architect's, at 12-03 (the roadmap's step: "the pilot's gate written").
- **The gate is per lineage, so per domain** (§7.5). `cli.py inferred-gate --element … --lineage …` reads one lineage's report against the written sample and margin. The sample counts that lineage's scored claims, one per game, side and read. Claims from several domains are never pooled into one sample, because the same game-side read from D domains would reach the sample D times as fast on correlated claims. The unit is written with the sample (§12(k)).
  - It prints PASS, FAIL, or NOT YET (the sample is not reached), and writes nothing else.
  - A tie is a rejection.
- **What a PASS allows.** An element that passes may only be DECLARED as an input to a candidate, which then runs at that sport's UNCHANGED gate (375 item 2(d)). Nothing inferred changes a call or a stake before its gates (375 item 2(k)).
- **For the NHL starting goalie, 496 item 4(a) closes the quantity the ceiling read:** "I build no as-of estimate and no projected starter of this quantity as an NHL model input." 496 item 4(d) says no NHL model input waits on the pilot. A goalie route in another form is not closed: it "is a new idea and declares 2026-27" (491 item 6(a); 496 item 4(c)). §7.6 sets out what the pilot is then for.

### 7.5 Lineage (375 item 2(h))

- A lineage is the element, plus the domain (§3.2), plus the provider's model, plus the prompt's sha256. A new model, a new prompt or a new domain starts a new lineage, and no row is ever regenerated. So a claim's successor (§9) is always the same source's later claim, a change of mind (375 item 2(b)), never another domain's.
- A destroyed source's rows leave their lineage. The report prints that as a count, so a lineage is never silently rescored.
- The 11-14 proposal called this a "series". It is renamed here because `nhl_landing.py` already uses "series" for its polls (`SERIES_SCOPE`, addendum 343 item 1).

### 7.6 What the NHL pilot would measure now that no NHL model input waits on it (496 item 4(d))

This paragraph sets out readings; it chooses none, and the architect rules on 12-03. Since 496, no NHL model input waits on the pilot (496 item 4(d)): the projected starter of the ceiling's quantity is closed as an input (4(a)), and a goalie route in another form would be a new idea declared on 2026-27 (491 item 6(a); 496 item 4(c)). The pilot's own measure (§7.3: the inferred starter against the truth, by status word and lead time, against the free baselines, with its calls and tokens counted) is unchanged by that. What changes is what its result would be for:
- **(A) A test of the layer's method.** The goalie is the one element whose truth arrives after every game. The pilot would measure whether a fixed-source reader names a fact better than the free baselines, how early and at what cost. The result would decide whether the layer is built for the sports that follow in 375 item 1(v)'s order. No NHL model input waits on it.
- **(B) Labelled context beside the NHL's market-only pages.** The starter would be shown as reading, never as a model input. Under 375 item 1(iv) it would appear only after the first scored read; the score would tell a reader how far to trust the label.
- **(C) The pilot moves to an element that a model input does wait on**, in a later sport of 375 item 1(v)'s order. NHL goalies would not be built. This would change 375 item 1(i)'s "ONE pilot, NHL starting goalies", which is the architect's to change, and it would rewrite §7.1 to §7.3 and §10 for that element.
- **(D) No pilot for now.** The design would stand as the record, and nothing would be built until a lane names an input that waits on the layer.

Under (A) and (B), §§1 to 11 stand as written. Under (C), the truth, the baselines, the sources and the cost change with the element. Under (D), this document is the only output.

## 8. What leaves the host (375 item 4(b): "scores and labelled summaries to the private mirror, nothing else")

- **The summary:** `exports/inferred/<element>.md`, holding the gate report's counts and shares, labelled "inferred, shadow, not a fact".
- **It needs a SECOND kept subtree in `exports_mirror.py`:** `exports/inferred/** -> <role>/inferred/**`, .md only, the way 250 item 4 ruled the first (bulletins). Today the mirror carries no subfolder but `bulletins/**` (§12(c)).
- **The other carriers.** `pull_exports.py` never reaches the subtree, because it lists the top level only. No test on main pins that yet; the build adds one (§1). `sp_migrate.py pack` leaves it out (§1).
- **What never leaves:** no row, no name, no evidence text and no NBA content (368 item 3(a)).
- **Bulletins:** inferred context reaches a bulletin only after the pilot's first scored read (375 item 1(iv)).

## 9. The graph (379 item 2's node shape)

- **The second input.** The rebuild gains `--private-backup-dir`. It opens the private BACKUPS `?mode=ro&immutable=1`, never the live stores, and projects their rows by kind plus tier (§3.4).
  - This adds a second input to the graph, whose scope 252 item 4 and 347 item 5(b) rule as "reading a `.backup` COPY of the database". So the second input is the architect's to rule (§12(i)).
- **An inferred claim is a node** (379 item 2), with edges:
  - to its evidence: one node per cited page, carrying the shown publication time;
  - to its successor: the next claim in its lineage (so from the same domain, §7.5) for the same game, side and element;
  - to its truth: the side's truth as §7.1 defines it, once stored, or no truth edge where the side has none.

  An api fact for the same question is its own node, and the precedence of §3.4 is read on the projection.
- **The unit.** The graph unit runs as sp under `ProtectSystem=strict`, with `InaccessiblePaths=/etc/sports-predictor` and data/ masked read-only by `TemporaryFileSystem` (378 item 3).
  - Its header records why data/ is masked and not inaccessible: an `InaccessiblePaths` data/ made the `check_db` fence refuse every run.
  - The same care applies here. The live stores under `SP_PRIVATE_DIR` are hidden from the graph unit by `TemporaryFileSystem=<SP_PRIVATE_DIR>:ro`, which the fence never walks. The private backups stay readable.
  - A test pins the line.
  - Mode 0700 gives no isolation between sp's own units, so every other sp unit that does not need the live stores gets the same line.
- **The graph file** stays on the host (`logs/availability/graph`, never mirrored, never backed up). §4 removes it on a destroy, holding the rebuild's own lock (`logs/availability/graph/.rebuild.lock`), and the next run of the unit rebuilds it.

## 10. The cost estimate for the NHL pilot, in tokens and calls (376 item 3)

These are estimates, to be replaced by the bench's measured figures. No dollar figure is written (376 item 2(c)). **They are for ONE domain (D = 1).** One call reads one domain (§3.2), so with D listed domains every call, token and fetch figure below is multiplied by D. The domains are named in the reader's PR (§5), and the bench's call and page bounds are set from D.
- **Volume:** about 1,312 games over about 180 days, so 7 to 8 games on an average day and up to 16 on a full slate.
- **Per game, per domain:** two calls, a morning read (T-8h) and a late read (T-90).
  - Each call is about 6,000 input tokens (about 2,500 a team from one domain's trimmed pages, plus the prompt and the facts) and about 300 output tokens.
  - That is about 12,000 input and 600 output tokens a game.
- **Per day:**
  - about 16 calls on an average day: about 95,000 input and 5,000 output tokens;
  - about 32 calls on a full slate: about 190,000 input and 10,000 output tokens.
- **Bench:** a test of 10 games and 20 calls is about 120,000 input and 6,000 output tokens.
- **Fetches:** about 4 pages a game per read per domain, two a team. The bench's page bound is set on that, times D.

## 11. The NBA report (368): source `nba_injury_report`, tier api, in its own folder

- **The parse.** The report's rows become `injury_status`, with the league's words verbatim in `attrs`. `source_stamp` is the report's own publication time, the stamp the probe's `STAMP_STRICT` reads. The parse waits on the report console's form.
- **The conditions of 368 item 3** hold:
  - one fetch per published report;
  - the plain User-Agent;
  - no crawl;
  - the terms phase re-run before enabling and at each season's start, with a changed date line going to the architect before the next fetch;
  - the destroy path on any objection.
- **No NBA statistic from nba.com, ever** (368 item 3(b)).
- **Its report phase** is the architect's block on the host (368 item 4; 492 item 4). Its rows live in this source's store, never in sports.db (368 item 3(a)).
- **Tests.** Every test of the store, the plugs, the bench, the score and the destroy holds synthetic shapes only, on the throwaway DB and a temporary private folder (368 item 3(a)).

## 12. For the architect's ruling, 2026-12-03

- (a) Per-source folders, each with per-tier tables (§1), against one private store with per-tier tables. Both keep the two tiers in separate tables. Per source makes a destroy one folder, never a DELETE.
- (b) One domain per call (§3.2), so every claim depends on one source and a destroy never touches another source's rows, with the evidence rule that enforces it (§1.1) and one `sp-inferred@` instance per domain. The alternative is one inferred store with a per-domain DELETE exception against 368 item 3(d). Its cost is D times the calls (§10).
- (c) The second kept subtree in `exports_mirror` (§8).
- (d) The market-word list and the trim rule (§5), as data. The proposal:
  - the words: odds, line, spread, moneyline, sportsbook, betting, and a signed price such as +/-<digits>;
  - the trim: keep a paragraph only if it names a listed goalie, or names both teams and the date.
- (e) The cap's unit: calls and tokens, against 375 item 1(iii)'s "spend cap". Its two NAMES; the calls ledger that counts them (§1.1, §6); and the register's path and shape (§5, §7.4).
- (f) The pilot's truth, its rule for a side with two goalies in net, its name-to-id rule and its baselines (§7.1, §7.2). Keeping the landing projection out of the model's inputs (§5).
- (g) 376 item 3's question: the fixed list of domains, fetched by the reader (§5).
- (h) The key (§3.3). (A), proposed: its value in host.env as ruled, with `UnsetEnvironment` on the other eleven units, readable by any sp process as every other provider key is today. (B): hiding host.env from the units that read no role, which cannot include the chains. (C): a root-only second file passed to the reader alone, which departs from 376 item 1(a). Hiding host.env from every unit is not offered: under 116 item 2 it makes the host's role unknown.
- (i) The graph's second input, and the node shape of an inferred claim (§9).
- (j) What the NHL pilot is now for (§7.6). This document does not choose.
- (k) The pilot's gate: its sample and the sample's unit (one claim per game, side and read, per lineage, never pooled across domains), its margin, its lead-time buckets, its confidence bands and its lineage's declared start (§5, §7.3, §7.4). The private backups' retention (§2).
- (l) Choices in the body that change or add to something already built or ruled:
  - the NBA probe's receipts moving from 368 item 4(ii)'s `logs/availability/` (§4);
  - the destroy's `--also` list until then (§4);
  - the new kind `inferred_starter`, and the kind-plus-tier precedence (§3.4);
  - the bench's `INVOCATION_ID` refusal (§6);
  - the masking line on every sp unit that does not need the live stores (§9);
  - the first private migrate file (§1.4);
  - the source lock that every writer and the destroy hold, and the graph rebuild's own lock (§4);
  - the token reservation before each timer call, with `max_retries=0` (§3.3, §6);
  - the templated `sp-inferred@` unit (§3.2).

## 13. Since the proposal of 11-14: the repository facts re-read on main `822ff041`

- **`install.sh`.** The proposal said it "runs unconditionally on every deploy that ships a unit file". It does not: the deploy never calls it, and it runs only in the architect's enabling blocks (374 item 2). The conclusion stands (§1): the block makes the folders.
- **The graph unit.** The proposal put `SP_PRIVATE_DIR` in `InaccessiblePaths` "beside data/". Since 378 item 3, data/ is masked by `TemporaryFileSystem`, because an inaccessible data/ refused every run. §9 follows the masked form.
- **The NBA probe's receipts.** The proposal said "one `--out` default change". `--out` has no default; the report phase requires it under `logs/availability/` (`refuse_report_out`). §4 changes that rule.
- **host.env and the key.** host.env.example says keys do not live there, and eleven units load the file. §3.3 sets both facts out for (h). host.env is root:sp 0640 and is re-read in-process, so `UnsetEnvironment` alone cannot keep the key from a unit (Codex's review of #1112; my own review had wrongly refuted this). Hiding the file is not a fix either: `desk_policy` reads the role from it strictly, and by 116 item 2 an unreadable host.env makes the role unknown.
- **The secret lists.** `record._SECRET_ENV` lacks `API_BASKETBALL_KEY`, which `sp_common.SECRET_ENV` has. §3.3.
- **The carriers.** `sp_migrate.py pack` copies `exports/` recursively, and `pull_exports`' `--remote-dir` override reads `SP_HOST_EXPORTS`. §1 pins both.
- **The lists.** No test ties `TIMERS_BY_BLOCK` to THE HELD LIST; THE HELD LIST is two entries now. §3.5.
- **`not_host_reason`** is in `src/walters/desk_policy.py`. **The readiness predicate's pattern** takes a session (`record.migrated(rs)`).
- **Inside the proposal.** Its four lead-time buckets could not be filled by its two reads (§7.3), and its landing baseline does not exist before T-120 (§7.2). "series" is renamed "lineage" (§7.5).
- **Rulings since the proposal:**
  - 379 item 2 (the graph's node shape, §9);
  - 428 item 5(b) (the landing listing is not a pregame signal, §7.2);
  - 491 and 496 (the true-starter ceiling is FALSE, and the pilot's purpose is open, §7.4 and §7.6);
  - 501 (the four texts, §0.3).
