from purrge.app import run_headless
from purrge.cleaners import cleanresult
from purrge.config import load


class fakecleaner:
    name = "temp"

    def clean(self):
        return cleanresult(self.name, freed_bytes=100, items=3)


def test_run_headless_updates_all_time_total(tmp_path, capsys):
    p = tmp_path / "config.json"
    results = run_headless(cleaners=[fakecleaner()], path=p)
    assert results[0].freed_bytes == 100
    assert load(p).total_freed_bytes == 100
    out = capsys.readouterr().out
    assert "temp" in out
    assert "purrge" in out
