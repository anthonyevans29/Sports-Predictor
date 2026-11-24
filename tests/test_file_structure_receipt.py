"""The file structure receipt (DEV 4, Lane D; the brief of addendum 518 item 5; Refs #105, #838): read-only, on
synthetic files under pytest's tmp_path only. No real file, no data/ path is ever created or opened."""
import gzip
import hashlib
import importlib.util
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "file_structure_receipt.py"
spec = importlib.util.spec_from_file_location("file_structure_receipt", SCRIPT)
fsr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fsr          # dataclasses resolve their module by name while the class is built
spec.loader.exec_module(fsr)

SENTINEL = "ZQXSECRETVALUE"          # a value of a column nobody names: it must never be printed
CSV = (
    "season,game_type,team,xg,when,flag,day,stamp,note\n"
    "2023,2,AAA,0.12,2023-10-10,true,20231010,2023-10-10T19:00:00Z,\n"
    "2023,3,BBB,NA,2023-10-11,FALSE,20231011,2023-10-11T19:30:00Z,   \n"
    "2024,2," + SENTINEL + ",1.5e0,2024-01-02,true,20240102,2024-01-02T00:05:00+01:00,x\n"
)


def run(argv):
    lines = []
    code = fsr.main(argv, out=lines.append)
    return code, "\n".join(lines)


def col_line(text, name):
    for ln in text.splitlines():
        if ln.strip().startswith("COL ") and "'{}'".format(name) in ln:
            return ln
    raise AssertionError("no COL line for " + name)


def tree(p: Path):
    return sorted((str(x.relative_to(p)), x.stat().st_size, x.stat().st_mtime_ns) for x in p.rglob("*"))


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "files"
    d.mkdir()
    (d / "a.csv").write_text(CSV, encoding="utf-8")
    with gzip.open(d / "a.csv.gz", "wb") as f:
        f.write(CSV.encode("utf-8"))
    with zipfile.ZipFile(d / "z.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("inner/a.csv", CSV)
        z.writestr("readme.txt", "not a csv")
    (d / "notes.txt").write_text("skip me " + SENTINEL, encoding="utf-8")
    return d


# ---- what it prints ---------------------------------------------------------------------------------------------


def test_kinds_shares_min_max_and_distinct(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text(CSV, encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    assert "rows 3 · columns 9 · blank records 0 · ragged rows 0" in text
    assert "kind int · null 0.0% · empty 0.0% · distinct 2 · min 2023 · max 2024" in col_line(text, "season")
    assert "kind float · null 33.3%" in col_line(text, "xg") and "min 0.12 · max 1.5e0" in col_line(text, "xg")
    assert "kind date" in col_line(text, "when") and "min 2023-10-10 · max 2024-01-02" in col_line(text, "when")
    assert "kind bool" in col_line(text, "flag") and "min" not in col_line(text, "flag")
    assert "valid YYYYMMDD date" in col_line(text, "day")
    st = col_line(text, "stamp")
    assert "kind datetime (with a zone)" in st
    # min and max by instant, not by text: 2024-01-02T00:05+01:00 is 2024-01-01T23:05Z, still the max
    assert "min 2023-10-10T19:00:00Z · max 2024-01-02T00:05:00+01:00" in st
    note = col_line(text, "note")
    assert "kind text" in note and "empty 66.7%" in note and "distinct 1" in note and "min" not in note
    team = col_line(text, "team")
    assert "kind text · null 0.0% · empty 0.0% · distinct 3" in team and "min" not in team


def test_size_and_sha256_of_the_bytes_on_disk(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes(CSV.encode("utf-8"))
    code, text = run([str(p)])
    assert code == 0
    assert "bytes {} · sha256 {}".format(len(CSV.encode()), hashlib.sha256(CSV.encode()).hexdigest()) in text


def test_gz_and_zip_members_report_both_hashes(folder):
    code, text = run([str(folder)])
    assert code == 0
    raw = CSV.encode("utf-8")
    gz = (folder / "a.csv.gz").read_bytes()
    zp = (folder / "z.zip").read_bytes()
    assert "bytes {} · sha256 {}".format(len(gz), hashlib.sha256(gz).hexdigest()) in text
    assert "decompressed bytes read {} · sha256 {}".format(len(raw), hashlib.sha256(raw).hexdigest()) in text
    assert "FILE {}/z.zip!inner/a.csv".format(folder) in text
    assert "archive bytes {} · archive sha256 {}".format(len(zp), hashlib.sha256(zp).hexdigest()) in text
    assert "member bytes read {} · member sha256 {}".format(len(raw), hashlib.sha256(raw).hexdigest()) in text
    assert "SKIPPED {}/z.zip!readme.txt".format(folder) in text
    assert "SKIPPED {}/notes.txt".format(folder) in text
    assert "SUMMARY: read whole 3 · not read whole 0 · skipped 2 · EXIT 0" in text


def test_vocab_lists_values_and_counts_of_a_named_column_only(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text(CSV, encoding="utf-8")
    code, text = run([str(p), "--vocab", "game_type", "--vocab", "absent_col"])
    assert code == 0
    assert "VOCAB COL 2 'game_type' (2 distinct, 3 cells):" in text
    assert "    '2' 2" in text and "    '3' 1" in text
    assert "VOCAB 'absent_col': no file read has a column with that exact name" in text


def test_vocab_counts_null_and_empty_cells_and_caps_the_listing(tmp_path):
    p = tmp_path / "v.csv"
    p.write_text("k\n" + "a\n" * 5 + "b\n" * 3 + "c\n" + "NA\n" + "\n" + " \n", encoding="utf-8")
    code, text = run([str(p), "--vocab", "k", "--vocab-max", "2"])
    assert code == 0
    assert "blank records 1" in text                    # an empty line is a blank record, not a row
    assert "VOCAB COL 1 'k' (5 distinct, 11 cells):" in text
    assert "    'a' 5" in text and "    'b' 3" in text
    assert "... and 3 more values (3 cells)" in text


def test_distinct_cap(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("n\n" + "".join("{}\n".format(i) for i in range(50)), encoding="utf-8")
    code, text = run([str(p), "--distinct-cap", "10", "--vocab", "n"])
    assert code == 0
    assert "distinct more than 10 (cap)" in col_line(text, "n")
    assert "VOCAB COL 1 'n': more than 10 distinct values, null and empty cells included (cap); not listed" in text
    assert "min 0 · max 49" in col_line(text, "n")


def test_ragged_rows_are_counted_and_absent_cells_shared(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("a,b,c\n1,2,3\n4,5\n6,7,8,9\n", encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    assert "rows 3 · columns 3 · blank records 0 · ragged rows 2" in text
    assert "absent 33.3%" in col_line(text, "c")


def test_mixed_kinds_are_text_and_print_no_value(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("x,d,t\n1,2024-01-01,2024-01-01T10:00:00Z\nabc,03/04/2024,2024-01-02T10:00:00\n", encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    for name in ("x", "d", "t"):
        assert "kind text" in col_line(text, name) and "min" not in col_line(text, name)


def test_quoted_fields_with_newlines_are_one_record(tmp_path):
    p = tmp_path / "q.csv"
    p.write_text('a,b\n"line one\nline two",2\n', encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    assert "rows 1 · columns 2" in text


def test_delimiter_and_encoding_are_options_never_guesses(tmp_path):
    p = tmp_path / "s.csv"
    p.write_bytes("nom;ville\nél;Montréal\n".encode("latin-1"))
    code, text = run([str(p), "--delimiter", ";", "--encoding", "latin-1"])
    assert code == 0
    assert "columns 2" in text and "'ville'" in text
    code, text = run([str(p)])          # the default utf-8-sig cannot decode latin-1 bytes: not read whole
    assert code == 1
    assert "ERROR: not read whole" in text and "UnicodeDecodeError; encoding utf-8-sig" in text


def test_a_header_that_looks_like_data_is_withheld(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("2023," + SENTINEL + ",3.5\n2024,x,4.5\n", encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    assert "HEADER WITHHELD: 2 of 3 header cells" in text
    assert "COL 1 #1" in text and SENTINEL not in text and "'2023'" not in text


def test_an_empty_file_is_read_whole(tmp_path):
    p = tmp_path / "e.csv"
    p.write_bytes(b"")
    code, text = run([str(p)])
    assert code == 0
    assert "rows 0 · columns 0" in text


# ---- what it never prints -----------------------------------------------------------------------------------------


def test_no_row_and_no_value_of_an_unnamed_column_is_printed(folder):
    code, text = run([str(folder), "--vocab", "season"])
    assert code == 0
    assert SENTINEL not in text
    for row in CSV.splitlines()[1:]:
        assert row not in text
    assert "AAA" not in text and "BBB" not in text


def test_a_decode_error_never_prints_the_bytes(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_bytes(b"a,b\n1,2\n3," + SENTINEL.encode() + b"\xff\xfe\n")
    code, text = run([str(p)])
    assert code == 1
    assert SENTINEL not in text and "\\xff" not in text and "0xff" not in text
    assert "ERROR: not read whole, at record 1, or after it (UnicodeDecodeError; encoding utf-8-sig)" in text


def test_the_command_line_prints_nothing_of_a_row_on_stdout_or_stderr(folder):
    res = subprocess.run([sys.executable, str(SCRIPT), str(folder), "--vocab", "season"],
                         capture_output=True, text=True, cwd=str(folder.parent))
    assert res.returncode == 0, res.stdout + res.stderr
    assert SENTINEL not in res.stdout and SENTINEL not in res.stderr
    assert res.stderr == ""


# ---- what it refuses ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["data", "DATA", "Data"])
def test_a_path_under_a_folder_named_data_is_refused_before_anything_opens(tmp_path, name):
    d = tmp_path / name
    d.mkdir()
    (d / "a.csv").write_text(CSV, encoding="utf-8")
    code, text = run([str(d / "a.csv")])
    assert code == 2
    assert "REFUSED" in text and "law 5" in text and "COL " not in text and "\nFILE " not in text
    code, text = run([str(d)])
    assert code == 2 and "\nFILE " not in text


def test_the_checkout_data_dir_is_refused_and_never_created(tmp_path):
    target = ROOT / "data" / "no_such_file_fsr.csv"
    existed = (ROOT / "data").exists()
    code, text = run([str(target)])
    assert code == 2 and "REFUSED" in text
    assert not target.exists()
    assert (ROOT / "data").exists() == existed


def test_a_symlink_into_data_is_refused(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.csv").write_text(CSV, encoding="utf-8")
    clean = tmp_path / "clean"
    clean.mkdir()
    try:
        os.symlink(d / "a.csv", clean / "link.csv")
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    code, text = run([str(clean / "link.csv")])
    assert code == 2 and "REFUSED" in text
    code, text = run([str(clean)])                     # found inside a folder: refused too, before any file opens
    assert code == 2 and "\nFILE " not in text


def test_the_checkout_data_resolution_rule(tmp_path):
    """sp_common's rule, written out: a path that resolves under ROOT/data is refused even if no part is named
    data as given; checked against a stand-in root under tmp_path so the checkout's data/ is never touched."""
    fake_root = tmp_path / "checkout"
    (fake_root / "data").mkdir(parents=True)
    assert fsr.data_refusal(fake_root / "data" / "x.csv", root=fake_root) is not None
    assert fsr.data_refusal(tmp_path / "elsewhere" / "x.csv", root=fake_root) is None


def test_a_data_folder_inside_a_recursive_walk_is_refused(tmp_path):
    top = tmp_path / "top"
    (top / "sub" / "Data").mkdir(parents=True)
    (top / "sub" / "a.csv").write_text(CSV, encoding="utf-8")
    code, text = run([str(top), "--recursive"])
    assert code == 2 and "\nFILE " not in text
    code, text = run([str(top)])                       # not recursive: subfolders are never entered
    assert code == 1 and "NOTHING READ" in text


@pytest.mark.parametrize("argv,needle", [
    ([], "name at least one PATH"),
    (["x.csv", "--delimiter", ";;"], "--delimiter must be one character"),
    (["x.csv", "--encoding", "no-such-codec"], "not a text encoding Python knows"),
    (["x.csv", "--encoding", "hex"], "not a text encoding Python knows"),          # a bytes codec, refused first
    (["x.csv", "--delimiter", '"'], "not a quote or a line break"),
    (["x.csv", "--vocab-max", "0"], "--vocab-max must be 1 or more"),
    (["x.csv", "--distinct-cap", "0"], "--distinct-cap must be 1 or more"),
])
def test_bad_options_are_refused(argv, needle):
    code, text = run(argv)
    assert code == 2 and needle in text


# ---- what it cannot read whole ------------------------------------------------------------------------------------


def test_a_missing_path_exits_1_and_the_others_are_still_read(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text(CSV, encoding="utf-8")
    code, text = run([str(tmp_path / "nope.csv"), str(p)])
    assert code == 1
    assert "MISSING" in text and "rows 3" in text
    assert "SUMMARY: read whole 1 · not read whole 1" in text


def test_a_truncated_gz_exits_1(tmp_path):
    good = gzip.compress((CSV * 200).encode("utf-8"))
    p = tmp_path / "t.csv.gz"
    p.write_bytes(good[: len(good) // 2])
    code, text = run([str(p)])
    assert code == 1 and "ERROR: not read whole" in text and "EOFError" in text


def test_a_corrupt_gz_exits_1(tmp_path):
    p = tmp_path / "c.csv.gz"
    p.write_bytes(b"this is not gzip at all")
    code, text = run([str(p)])
    assert code == 1 and "ERROR: not read whole" in text


def test_a_zip_member_with_a_bad_crc_exits_1(tmp_path):
    p = tmp_path / "b.zip"
    payload = (CSV * 50).encode("utf-8")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as z:
        z.writestr("a.csv", payload)
    raw = bytearray(p.read_bytes())
    i = raw.find(b"2023,3,BBB")
    raw[i] = ord("9")                                  # one stored byte changed: the member's CRC no longer holds
    p.write_bytes(bytes(raw))
    code, text = run([str(p)])
    assert code == 1 and "BadZipFile" in text


def test_a_file_that_is_not_a_zip_exits_1(tmp_path):
    p = tmp_path / "n.zip"
    p.write_bytes(b"not a zip")
    code, text = run([str(p)])
    assert code == 1 and "not a readable zip archive" in text


def test_a_zip_with_no_csv_member_exits_1(tmp_path):
    p = tmp_path / "o.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("x.txt", "hello")
    code, text = run([str(p)])
    assert code == 1 and "holds no member named .csv" in text


def test_a_csv_error_exits_1(tmp_path):
    p = tmp_path / "nul.csv"
    p.write_bytes(b"a,b\n1,2\n3,\x004\n")
    code, text = run([str(p)])
    # 3.10's csv refuses a NUL and 3.11+ would read it: the receipt refuses it on every Python, the same way
    assert code == 1
    assert "ERROR: not read whole, at record 3, or after it (a NUL character in the text)" in text


# ---- what it writes: nothing --------------------------------------------------------------------------------------


def test_it_writes_nothing(folder):
    before = tree(folder.parent)
    res = subprocess.run([sys.executable, str(SCRIPT), str(folder), "--recursive", "--vocab", "team"],
                         capture_output=True, text=True, cwd=str(folder.parent))
    assert res.returncode == 0, res.stdout
    assert tree(folder.parent) == before


def test_python_310_floor_no_fstrings_at_all():
    """No f-string at all, so none can span lines or reuse its quote (PEP 701; CONTRIBUTING.md's 3.10 floor)."""
    import io
    import tokenize
    src = SCRIPT.read_text(encoding="utf-8")
    compile(src, str(SCRIPT), "exec")
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        name = tokenize.tok_name[tok.type]
        assert name != "FSTRING_START", tok
        if name == "STRING":
            prefix = tok.string[: len(tok.string) - len(tok.string.lstrip("rRbBuUfF"))]
            assert "f" not in prefix.lower(), tok


def test_a_zip_member_named_data_is_not_a_path_on_disk(tmp_path):
    """ARCHITECT 2026-11-24, addendum 521 item 6 Q1: "A member's name inside a zip is not a path on disk and is not
    refused for holding that word." The archive itself sits outside any data/ directory."""
    p = tmp_path / "m.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("data/shots.csv", CSV)
    code, text = run([str(p)])
    assert code == 0 and "REFUSED" not in text
    assert "FILE {}!data/shots.csv".format(p) in text and "rows 3" in text


# ---- the review's findings, pinned (each found and reproduced before the PR) ---------------------------------------


def test_an_unclosed_quote_is_an_error_never_a_silent_merge(tmp_path):
    p = tmp_path / "u.csv"
    p.write_text('a,b\n1,"x\n2,y\n3,z\n4,w\n', encoding="utf-8")
    code, text = run([str(p)])
    assert code == 1
    assert "ERROR: not read whole, at record 2, or after it (csv.Error" in text
    assert "PARTIAL (up to the error) rows 0" in text


def test_a_character_after_a_closing_quote_is_an_error(tmp_path):
    p = tmp_path / "q.csv"
    p.write_text('a,b\n1,"x"y\n', encoding="utf-8")
    code, text = run([str(p)])
    assert code == 1 and "csv.Error" in text


def test_blank_lines_before_the_header_are_blank_records(tmp_path):
    p = tmp_path / "lead.csv"
    p.write_text("\n\na,b\n1,2\n3,4\n", encoding="utf-8")
    code, text = run([str(p), "--vocab", "a"])
    assert code == 0
    assert "rows 2 · columns 2 · blank records 2 · ragged rows 0" in text
    assert "VOCAB COL 1 'a' (2 distinct, 2 cells):" in text and "no file read has" not in text


@pytest.mark.parametrize("first", ["Federer,NA,true", "Federer,Nadal,Wimbledon,R,true"])
def test_a_header_with_a_bool_or_null_cell_is_withheld(tmp_path, first):
    p = tmp_path / "h.csv"
    second = "Djokovic,NA,false" if first.count(",") == 2 else "Djokovic,Murray,Wimbledon,L,false"
    p.write_text(first + "\n" + second + "\n", encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    assert "HEADER WITHHELD" in text and "Federer" not in text and "Djokovic" not in text


def test_a_header_cell_that_recurs_as_its_own_columns_value_is_withheld(tmp_path):
    p = tmp_path / "w.csv"
    p.write_text("Alpha,Wimbledon\nBravo,Wimbledon\nCharlie,Paris\n", encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    assert "HEADER WITHHELD: 1 of 2" in text and "Alpha" not in text and "Wimbledon" not in text


def test_a_real_header_is_not_withheld(tmp_path):
    p = tmp_path / "ok.csv"
    p.write_text(CSV, encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0 and "HEADER WITHHELD" not in text


def test_an_int_cell_past_the_digit_limit_is_read(tmp_path):
    p = tmp_path / "big.csv"
    p.write_text("n\n" + "1" * 5000 + "\n3\n", encoding="utf-8")
    ok = tmp_path / "ok.csv"
    ok.write_text(CSV, encoding="utf-8")
    code, text = run([str(p), str(ok)])
    assert code == 0
    assert "kind int" in col_line(text, "n") and "min 3 · max" in col_line(text, "n")
    assert "SUMMARY: read whole 2" in text
    if hasattr(sys, "get_int_max_str_digits"):
        assert sys.get_int_max_str_digits() != 0           # the interpreter's limit is restored after the run


def test_any_decompressor_error_is_an_error_line_and_later_files_are_read(tmp_path):
    import random
    rows = "a,b\n" + "".join("{},{}\n".format(i, i * 7) for i in range(20000))
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_LZMA) as zf:
        zf.writestr("a.csv", rows)
    raw = bytearray(z.read_bytes())
    rnd = random.Random(7)
    start = len(raw) // 3
    for i in range(start, start + 64):
        raw[i] ^= rnd.randrange(1, 256)
    z.write_bytes(bytes(raw))
    ok = tmp_path / "b.csv"
    ok.write_text(CSV, encoding="utf-8")
    code, text = run([str(z), str(ok)])
    assert code == 1
    assert "ERROR: not read whole" in text and "FILE {}".format(ok) in text and "SUMMARY:" in text


def test_a_fifo_is_never_opened(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs here")
    d = tmp_path / "f"
    d.mkdir()
    os.mkfifo(str(d / "pipe.csv"))
    (d / "a.csv").write_text(CSV, encoding="utf-8")
    res = subprocess.run([sys.executable, str(SCRIPT), str(d)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0
    assert "pipe.csv (not a regular file; not opened)" in res.stdout
    res = subprocess.run([sys.executable, str(SCRIPT), str(d / "pipe.csv")], capture_output=True, text=True,
                         timeout=30)
    assert res.returncode == 1 and "not a regular file or a folder; not opened" in res.stdout


def test_subfolders_and_symlinked_folders_are_named_never_silently_dropped(tmp_path):
    top = tmp_path / "top"
    (top / "sub").mkdir(parents=True)
    (top / "a.csv").write_text(CSV, encoding="utf-8")
    (top / "sub" / "c.csv").write_text(CSV, encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "b.csv").write_text(CSV, encoding="utf-8")
    try:
        os.symlink(elsewhere, top / "linked")
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    code, text = run([str(top)])
    assert code == 0 and "sub (a subfolder; not entered without --recursive)" in text
    code, text = run([str(top), "--recursive"])
    assert code == 0 and "linked (a symlinked folder; not entered)" in text
    assert "FILE {}/sub/c.csv".format(top) in text and "b.csv" not in text


def test_an_unlistable_subfolder_exits_1(tmp_path, monkeypatch):
    top = tmp_path / "top"
    (top / "locked").mkdir(parents=True)
    (top / "a.csv").write_text(CSV, encoding="utf-8")
    real_scandir = os.scandir

    def scandir(path="."):
        if str(path).endswith("locked"):
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)
    monkeypatch.setattr(os, "scandir", scandir)            # root ignores chmod 000: the refusal is simulated
    code, text = run([str(top), "--recursive"])
    assert code == 1
    assert "ERROR {}/locked: a folder that could not be listed (PermissionError)".format(top) in text
    assert "FILE {}/a.csv".format(top) in text


def test_an_unlistable_folder_named_directly_exits_1(tmp_path, monkeypatch):
    d = tmp_path / "d"
    d.mkdir()
    ok = tmp_path / "ok.csv"
    ok.write_text(CSV, encoding="utf-8")

    def listdir(path="."):
        raise PermissionError(13, "Permission denied", str(path))
    monkeypatch.setattr(os, "listdir", listdir)
    code, text = run([str(d), str(ok)])
    assert code == 1 and "could not be listed (PermissionError)" in text and "FILE {}".format(ok) in text


def test_macos_metadata_is_skipped_in_zips_and_folders(tmp_path):
    blob = b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        " + b"\x00" * 64
    z = tmp_path / "mac.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("shots/shots.csv", CSV)
        zf.writestr("__MACOSX/shots/._shots.csv", blob)
    d = tmp_path / "tfold"
    d.mkdir()
    (d / "atp.csv").write_text(CSV, encoding="utf-8")
    (d / "._atp.csv").write_bytes(blob)
    code, text = run([str(z), str(d)])
    assert code == 0
    assert "__MACOSX/shots/._shots.csv (macOS metadata; not read)" in text
    assert "._atp.csv (macOS AppleDouble metadata; not opened)" in text
    assert "Mac OS X" not in text


def test_a_partial_file_prints_its_error_first_and_marks_every_figure(tmp_path):
    p = tmp_path / "p.csv"
    # past the decoder's first 1 MiB chunk, so the figures before the fault exist and must be marked PARTIAL
    p.write_bytes(b"a\n" + b"".join(str(i).encode() + b"\n" for i in range(300000)) + b"\xff\n")
    code, text = run([str(p)])
    assert code == 1
    lines = text.splitlines()
    i = lines.index("FILE {}".format(p))
    assert lines[i + 1].startswith("  ERROR: not read whole")
    assert any(ln.startswith("  PARTIAL (up to the error) rows") for ln in lines)
    assert any(ln.startswith("  PARTIAL (up to the error) COL 1") for ln in lines)


def test_small_shares_never_round_to_0_or_100(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("x,y\n" + "NA,5\n" + "1,NA\n" * 19999, encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    assert "null <0.1%" in col_line(text, "x") and "null >99.9%" in col_line(text, "y")


def test_names_print_with_control_characters_escaped(tmp_path):
    z = tmp_path / "inj.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.csv\n  COL 1 'fake' · kind int\nx.txt", "hello")
        zf.writestr("b.csv", CSV)
    code, text = run([str(z)])
    assert code == 0
    assert not any(ln.startswith("  COL 1 'fake'") for ln in text.splitlines())
    assert "a.csv\\n  COL 1 'fake'" in text


def test_vocab_blocks_name_their_column_position_on_duplicate_names(tmp_path):
    p = tmp_path / "dup.csv"
    p.write_text("x,y,x\n1,a,p\n2,b,q\n2,c,NA\n", encoding="utf-8")
    code, text = run([str(p), "--vocab", "x"])
    assert code == 0
    assert "DUPLICATE column names: 'x'" in text
    assert "VOCAB COL 1 'x' (2 distinct, 3 cells):" in text and "VOCAB COL 3 'x' (3 distinct, 3 cells):" in text


def test_only_ascii_digits_make_a_number_and_a_zone_minute_over_59_is_not_iso(tmp_path):
    p = tmp_path / "uni.csv"
    p.write_text("a,b,c\n\u0662\u0660\u0662\u0664\u0660\u0661\u0660\u0661,2024-01-01T10:00+01:99,\uff11\n"
                 "\u0662\u0660\u0662\u0664\u0660\u0661\u0660\u0662,2024-01-01T11:00+01:00,\uff12\n",
                 encoding="utf-8")
    code, text = run([str(p)])
    assert code == 0
    for name in ("a", "b", "c"):
        assert "kind text" in col_line(text, name), name


def test_an_unknown_user_is_refused_not_a_traceback():
    code, text = run(["~nosuchuserzz_fsr/a.csv"])
    assert code == 2 and "cannot be resolved" in text


# ---- the second review pass, pinned -------------------------------------------------------------------------------


def test_a_line_of_spaces_before_the_header_is_blank(tmp_path):
    p = tmp_path / "ws.csv"
    p.write_text(" \n , \na,b\n1,2\n3,4\n", encoding="utf-8")
    code, text = run([str(p), "--vocab", "a"])
    assert code == 0
    assert "rows 2 · columns 2 · blank records 2 · ragged rows 0" in text
    assert "VOCAB COL 1 'a'" in text


def test_the_recurrence_rule_holds_past_the_distinct_cap(tmp_path):
    p = tmp_path / "hl.csv"
    p.write_text("Hard,Wimbledon\nHard,Wimbledon\nClay,Roland Garros\nGrass,Halle\n", encoding="utf-8")
    for cap in ("100000", "2", "1"):
        code, text = run([str(p), "--distinct-cap", cap])
        assert code == 0
        assert "HEADER WITHHELD: 2 of 2" in text and "Hard" not in text and "Wimbledon" not in text, cap


@pytest.mark.parametrize("header,row", [
    ("shotID,season,game_id,team,homeTeamCode,awayTeamCode,event,xCord,yCord,shotType,goal,isHomeTeam,period,time",
     "{i},2023,2023020{i:03d},{side},TOR,MTL,{ev},{x},-12,WRIST,{g},1,2,{t}"),
    ("tourney_id,tourney_name,surface,draw_size,tourney_level,tourney_date,match_num,winner_id,winner_name,"
     "winner_hand,score,best_of,round,minutes",
     "2023-{i:04d},Event {i},Hard,32,A,20230102,{i},10{i:04d},Player {i},R,6-4 3-6 7-6(5),3,R32,{t}"),
])
def test_real_shaped_headers_are_not_withheld(tmp_path, header, row):
    rows = [row.format(i=i, side="HOME" if i % 2 else "AWAY", ev="SHOT" if i % 3 else "GOAL", x=i % 89,
                       g=1 if i % 3 == 0 else 0, t=100 + i) for i in range(1, 200)]
    p = tmp_path / "real.csv"
    p.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    code, text = run([str(p), "--vocab", "season" if "season" in header else "surface"])
    assert code == 0
    assert "HEADER WITHHELD" not in text and "rows 199 · columns 14" in text
    assert "kind int (every value is 8 digits and a valid YYYYMMDD date)" in text or "shotID" in text


def test_a_symlink_loop_is_read_the_same_on_every_python(tmp_path):
    d = tmp_path / "loop"
    d.mkdir()
    (d / "good.csv").write_text(CSV, encoding="utf-8")
    try:
        os.symlink("l2", str(d / "l1.csv"))
        os.symlink("l1.csv", str(d / "l2"))
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    code, text = run([str(d / "l1.csv")])                  # a named PATH that cannot be resolved: refused
    assert code == 2 and "cannot be resolved" in text
    code, text = run([str(d)])                             # an entry inside a folder: an ERROR, never opened
    assert code == 1 and "FILE {}".format(d / "good.csv") in text
    assert "l1.csv: cannot be resolved (" in text and "REFUSED" not in text


def test_shown_names_join_like_the_os(tmp_path):
    assert fsr._join("/", "bin") == "/bin"
    assert fsr._join("", "t.csv") == "t.csv"
    assert fsr._join("top", ".") == "top"
    assert fsr._join("a/", "b.csv") == "a/b.csv"


def test_an_odd_encoding_name_is_escaped(tmp_path):
    p = tmp_path / "e.csv"
    p.write_bytes(b"a\n\xff\n")
    code, text = run([str(p), "--encoding", "utf\n8"])
    assert code == 1
    assert not any(ln.startswith("8") for ln in text.splitlines())
    assert "encoding utf\\n8" in text


def test_a_collect_failure_still_ends_with_the_summary(tmp_path, monkeypatch):
    def boom(raws, recursive):
        raise OSError("simulated")
    monkeypatch.setattr(fsr, "collect", boom)
    code, text = run([str(tmp_path)])
    assert code == 1 and text.splitlines()[-1].startswith("SUMMARY:") and "simulated" not in text
