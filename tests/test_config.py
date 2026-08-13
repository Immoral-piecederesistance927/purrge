import json

from purrge.config import config, load, save


def test_load_missing_creates_defaults(tmp_path):
    p = tmp_path / "config.json"
    cfg = load(p)
    assert cfg.interval_minutes == 30
    assert cfg.cleaners == {"temp": True, "browser_cache": True, "ram_standby": True, "dns": True}
    assert p.exists()


def test_load_corrupt_regenerates(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{oops")
    assert load(p).interval_minutes == 30


def test_interval_clamped(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"interval_minutes": 999, "cleaners": {"temp": False}}))
    cfg = load(p)
    assert cfg.interval_minutes == 240
    assert cfg.cleaners["temp"] is False
    assert cfg.cleaners["dns"] is True


def test_save_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    cfg = load(p)
    cfg.interval_minutes = 45
    save(cfg, p)
    assert load(p).interval_minutes == 45
