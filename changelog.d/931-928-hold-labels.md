## 2026-11-11 (#931: 928-hold-labels — a held slate says so on its rows and page; refresh_seen names a held refresh; the runbook's lift step (ARCHITECT 2026-11-11, addendum 336 item 2; 337 items 1-2).)
- **Rulings (verbatim):**
  - Addendum 337 item 1: "the slate file and its page say "schedule not re-read: SP_SYNC_HOLD <code> — kickoffs as stored" on a held family's rows. That is display on a money-path file: it goes on #928 with the refresh_seen item and ships in that follow-up PR, not in #925."
  - Addendum 337 item 2: "lifting a hold: remove the code from the machine's one place, restart every long-running service that loaded it (the admin UI's unit, named), then read the by-place line on the next chain receipt — a code still listed under `environment` is a process that was not restarted".
  - Addendum 336 item 2: "Item 4 (ncaa_shadow.refresh_seen not naming the hold): the follow-up Issue, as proposed; read-only class."
- **Built:**
  - `closing.py`, the slate stage: when a schedule read of the slate is held, every row of the slate export carries `schedule_note` = `schedule not re-read: SP_SYNC_HOLD <code> — kickoffs as stored`.
    - The labelled document is written to its own file beside the kept export (`logs/<run id>.<stem>.schedule-note.json`, created once, never written over), and that file is linked into exports/. The export step's kept file is never written again (#442), so `export_written` still verifies.
    - The page carries the same text on its second line.
    - The slate receipt keeps `schedule_note` {file, text, rows, sha256}; `slate_file` names the labelled file's sha256.
    - A failed label write fails the slate as `slate rows not labelled`, its notice naming the cause: nothing linked, pushed or paged.
    - A slate with nothing held is unchanged.
  - `ncaa_shadow.refresh_seen`: a held refresh-by-id step (sp_run's `sync.held`, or the HELD line in its tail) reads state `none`, with `held` [codes] and `why` `the refresh-by-id step was HELD (SP_SYNC_HOLD <code>): it wrote nothing and no refresh_by_id receipt`. A step held for another code is not this competition's hold.
  - docs/specs/hosting-h1.md section O: the lift step in 337 item 2's words, with the host's lines (`sp-web.service`, the admin UI's unit) and the laptop's, a command that prints the receipt's `sync_hold` by place, and 336 item 2's sentence corrected. The held slate is quoted as ruled. Code's review found that the ruled check (the next chain receipt) cannot see a stale sp-web; the runbook names two checks that can, and the question is put to the architect.
- **Export contract (additive):** `schedule_note` on the rows of a held family's slate file only. No other file, row or field changes; no prediction, probability or Desk call changes.
- **Receipt:** the tests are listed in the PR body; each new test fails on main.

