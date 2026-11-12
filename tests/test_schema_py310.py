"""The availability triggers' rendered SQL, pinned (ARCHITECT 2026-11-07 07:05 ET, addendum 280 item 2(a)).

The 280 hotfix moved the snapshot hash guard's message (262 item 1) out of an f-string whose replacement field spanned
two lines (PEP 701: Python 3.12 only; a SyntaxError on the laptop's 3.10). "The trigger's text must stay
byte-identical": these values were rendered from main 231d81f5 (before the hotfix) on Python 3.12. The installed
trigger text is compared nowhere in the code (migrate_availability_record.py and src/availability/record.py read
triggers by NAME); this test is the receipt that a store created before the hotfix holds the text the code renders.
A trigger changed later by a ruling re-pins these values in that ruling's PR.

The 3.10 grammar itself is tested by CI's smoke-py310 job (parse, import smoke, this suite on 3.10): a SyntaxError
cannot be a fail-first test inside the interpreter that raises it (addendum 280 item 2(d)).
"""
import hashlib

from src.db import schema

SNAPSHOT_HASH_GUARD_231D81F5 = (
    "CREATE TRIGGER IF NOT EXISTS trg_availability_assertions_snapshot_hash_guard BEFORE INSERT ON "
    "availability_assertions BEGIN SELECT RAISE(ABORT, 'availability_assertions: an observation of a snapshot source "
    "asserts a row and keeps no payload_sha256: the hash is the load identity (addendum 262 item 1)') WHERE EXISTS "
    "(SELECT 1 FROM availability_observations o WHERE o.id = NEW.observation_id AND o.source IN "
    "('nflverse_depth_charts') AND o.payload_sha256 IS NULL); END")
ALL_SEVEN_SHA256_231D81F5 = "7ce26981c6b388fbfaabc32c5b98cf13e6ad5583aeae5ab4f777226e8702a47f"


def test_the_snapshot_hash_guard_renders_byte_identical_to_the_base():
    sql = {name: text for name, _table, text in schema.AVAILABILITY_TRIGGERS}
    assert sql["trg_availability_assertions_snapshot_hash_guard"] == SNAPSHOT_HASH_GUARD_231D81F5


def test_all_seven_availability_triggers_render_byte_identical_to_the_base():
    """The seven of 231d81f5, unchanged and first; #835 item 2 (addendum 258 item 2(2)) appends an eighth, its own
    trigger (CREATE TRIGGER IF NOT EXISTS never changes an installed one), pinned below."""
    assert len(schema.AVAILABILITY_TRIGGERS) == 8
    rendered = "\n".join(f"{name}\t{table}\t{text}" for name, table, text in schema.AVAILABILITY_TRIGGERS[:7])
    assert hashlib.sha256(rendered.encode()).hexdigest() == ALL_SEVEN_SHA256_231D81F5


POLL_GUARD_835 = (
    "CREATE TRIGGER IF NOT EXISTS trg_availability_observations_poll_guard BEFORE INSERT ON availability_observations "
    "BEGIN SELECT RAISE(ABORT, 'availability_observations: this poll is already observed (its row stands; "
    "append-only): the same source, endpoint and scheduled time (#835 item 2, addendum 258 item 2(2))') WHERE "
    "NEW.scheduled_at IS NOT NULL AND EXISTS (SELECT 1 FROM availability_observations x WHERE x.source = NEW.source "
    "AND x.endpoint = NEW.endpoint AND x.scheduled_at = NEW.scheduled_at); END")


def test_the_835_poll_guard_is_the_eighth_trigger_and_renders_as_pinned():
    name, table, text = schema.AVAILABILITY_TRIGGERS[7]
    assert (name, table) == ("trg_availability_observations_poll_guard", "availability_observations")
    assert text == POLL_GUARD_835
