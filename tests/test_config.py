import json

from purrge.config import config, load, save


def test_load_missing_creates_defaults(tmp_path):
    p = tmp_path / "config.json"
    cfg = load(p)
    assert cfg.interval_minutes == 30
    assert cfg.cleaners == {
        "temp": True,
        "browser_cache": True,
        "discord": True,
        "thumbnails": True,
        "crash_dumps": True,
        "shader_cache": True,
        "windows_update": True,
        "ram_standby": True,
        "dns": True,
    }
    assert cfg.total_freed_bytes == 0
    assert p.exists()


def test_total_freed_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    cfg = load(p)
    cfg.total_freed_bytes = 12345
    save(cfg, p)
    assert load(p).total_freed_bytes == 12345


def test_old_config_gains_new_keys(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"interval_minutes": 45, "cleaners": {"temp": False}}))
    cfg = load(p)
    assert cfg.interval_minutes == 45
    assert cfg.cleaners["temp"] is False
    assert cfg.cleaners["discord"] is True
    assert cfg.total_freed_bytes == 0


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


def test_theme_default_and_validation(tmp_path):
    p = tmp_path / "config.json"
    assert load(p).theme == "mocha"
    p.write_text(json.dumps({"theme": "latte"}))
    assert load(p).theme == "latte"
    p.write_text(json.dumps({"theme": "dracula"}))
    assert load(p).theme == "mocha"


def test_save_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    cfg = load(p)
    cfg.interval_minutes = 45
    save(cfg, p)
    assert load(p).interval_minutes == 45
