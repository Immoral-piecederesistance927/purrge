import os
import time

from purrge.cleaners import (
    browsercachecleaner,
    browserspec,
    cleanresult,
    discordcleaner,
    run_all,
    shadercleaner,
    sweep,
    tempcleaner,
    thumbcleaner,
    wercleaner,
    wucleaner,
)
from purrge.config import config


class boomcleaner:
    name = "temp"

    def clean(self):
        raise RuntimeError("boom")


class okcleaner:
    name = "dns"

    def clean(self):
        return cleanresult(self.name, items=1)


def test_run_all_survives_cleaner_crash():
    results = run_all(config(), cleaners=[boomcleaner(), okcleaner()])
    assert results[0].errors == 1
    assert results[1].items == 1


def test_run_all_respects_disabled():
    cfg = config()
    cfg.cleaners["temp"] = False
    assert run_all(cfg, cleaners=[boomcleaner()]) == []


def test_discord_cleaner_skips_when_running(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    f = cache / "data_0"
    f.write_text("x" * 5)
    spec = browserspec("discord", "discord.exe", tmp_path, ["cache"])
    r = discordcleaner(specs=[spec], running=lambda name: True).clean()
    assert r.name == "discord"
    assert f.exists()
    assert r.skipped == 1


def test_discord_cleaner_cleans_when_closed(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    f = cache / "data_0"
    f.write_text("x" * 5)
    spec = browserspec("discord", "discord.exe", tmp_path, ["cache"])
    r = discordcleaner(specs=[spec], running=lambda name: False).clean()
    assert not f.exists()
    assert r.freed_bytes == 5


def test_thumb_cleaner_only_touches_cache_dbs(tmp_path):
    db = tmp_path / "thumbcache_256.db"
    db.write_text("x" * 20)
    icon = tmp_path / "iconcache_32.db"
    icon.write_text("x" * 10)
    other = tmp_path / "notes.txt"
    other.write_text("keep")
    r = thumbcleaner(root=tmp_path).clean()
    assert not db.exists()
    assert not icon.exists()
    assert other.exists()
    assert r.freed_bytes == 30
    assert r.items == 2


def test_thumb_cleaner_missing_root(tmp_path):
    r = thumbcleaner(root=tmp_path / "nope").clean()
    assert r.items == 0


def test_shader_and_wer_cleaners_sweep_roots(tmp_path):
    f = tmp_path / "old.bin"
    f.write_text("x" * 7)
    make_old(f)
    assert shadercleaner(roots=[tmp_path]).name == "shader_cache"
    r = shadercleaner(roots=[tmp_path]).clean()
    assert r.freed_bytes == 7
    g = tmp_path / "report.wer"
    g.write_text("x" * 3)
    make_old(g)
    assert wercleaner(roots=[tmp_path]).clean().freed_bytes == 3


def test_supported_names_per_platform(monkeypatch):
    import sys
    from purrge.cleaners import supported_names
    monkeypatch.setattr(sys, "platform", "win32")
    assert "shader_cache" in supported_names()
    assert len(supported_names()) == 9
    monkeypatch.setattr(sys, "platform", "darwin")
    names = supported_names()
    assert names == ["temp", "browser_cache", "discord", "crash_dumps", "dns"]


def test_dns_command_per_platform(monkeypatch):
    import sys
    from purrge.cleaners import dns_command
    monkeypatch.setattr(sys, "platform", "win32")
    assert dns_command() == ["ipconfig", "/flushdns"]
    monkeypatch.setattr(sys, "platform", "darwin")
    assert dns_command() == ["dscacheutil", "-flushcache"]


def test_wu_cleaner_requires_admin(tmp_path, monkeypatch):
    import purrge.cleaners
    monkeypatch.setattr(purrge.cleaners, "is_admin", lambda: False)
    f = tmp_path / "old.cab"
    f.write_text("x")
    make_old(f)
    r = wucleaner(roots=[tmp_path]).clean()
    assert f.exists()
    assert r.skipped == 1
    monkeypatch.setattr(purrge.cleaners, "is_admin", lambda: True)
    r = wucleaner(roots=[tmp_path]).clean()
    assert not f.exists()


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


def test_browser_cleaner_skips_running_browser(tmp_path):
    cache = tmp_path / "default" / "cache"
    cache.mkdir(parents=True)
    f = cache / "f_000001"
    f.write_text("x" * 10)
    spec = browserspec("chrome", "chrome.exe", tmp_path, ["*/cache"])
    r = browsercachecleaner(specs=[spec], running=lambda name: True).clean()
    assert f.exists()
    assert r.skipped == 1


def test_browser_cleaner_cleans_closed_browser(tmp_path):
    cache = tmp_path / "default" / "cache"
    cache.mkdir(parents=True)
    f = cache / "f_000001"
    f.write_text("x" * 10)
    spec = browserspec("chrome", "chrome.exe", tmp_path, ["*/cache"])
    r = browsercachecleaner(specs=[spec], running=lambda name: False).clean()
    assert not f.exists()
    assert r.freed_bytes == 10
