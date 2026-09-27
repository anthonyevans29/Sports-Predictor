"""export-nfl-results is live-era: the fossil "rehearsal" field is gone (2026-09-27)."""
import json

from src.db.database import init_db


def test_results_export_has_no_rehearsal_field(tmp_path):
    init_db()
    from src.walters.nfl_predict import export_nfl_results
    doc = json.loads(open(export_nfl_results(out_dir=str(tmp_path))).read())
    assert "rehearsal" not in doc
    assert doc["sport"] == "nfl" and "results" in doc and "note" in doc
