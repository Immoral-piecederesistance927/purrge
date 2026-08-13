import os
import time

from purrge.cleaners import sweep, tempcleaner


def make_old(p):
    old = time.time() - 7200
    os.utime(p, (old, old))


def test_temp_cleaner_deletes_old_files(tmp_path):
    f = tmp_path / "old.log"
    f.write_text("x" * 100)
    make_old(f)
    r = tempcleaner(roots=[tmp_path]).clean()
    assert r.items == 1
    assert r.freed_bytes == 100
    assert not f.exists()


def test_temp_cleaner_keeps_fresh_files(tmp_path):
    f = tmp_path / "fresh.log"
    f.write_text("x")
    r = tempcleaner(roots=[tmp_path]).clean()
    assert r.items == 0
    assert r.skipped == 1
    assert f.exists()


def test_temp_cleaner_skips_locked_files(tmp_path):
    f = tmp_path / "locked.log"
    f.write_text("x")
    make_old(f)
    with open(f):
        r = tempcleaner(roots=[tmp_path]).clean()
    assert f.exists()
    assert r.skipped == 1


def test_sweep_removes_empty_dirs(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    f = d / "a.tmp"
    f.write_text("x")
    make_old(f)
    sweep(tmp_path, 3600)
    assert not d.exists()


def test_sweep_leaves_mei_dirs_alone(tmp_path):
    mei = tmp_path / "_mei12345"
    mei.mkdir()
    f = mei / "python311.dll"
    f.write_text("x")
    make_old(f)
    sweep(tmp_path, 3600)
    assert f.exists()


def test_sweep_missing_root(tmp_path):
    r = sweep(tmp_path / "nope")
    assert r.items == 0
