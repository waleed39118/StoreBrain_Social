from __future__ import annotations

from datetime import datetime, timedelta

from atheer.admin import run
from atheer.core.config import Settings


def test_admin_workflow(tmp_path, capsys):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'a.db'}", clinic_timezone="Asia/Riyadh", _env_file=None)
    assert run(["seed-demo"], settings) == 0
    assert run(["add-doctor", "--name", "Omar", "--specialty", "ENT", "--slot", "15"], settings) == 0
    assert run(["add-shift", "--doctor-id", "2", "--weekday", "mon", "--start", "09:00", "--end", "12:00"], settings) == 0
    assert run(["add-shift", "--doctor-id", "9", "--weekday", "mon", "--start", "09:00", "--end", "12:00"], settings) == 1

    # Next Monday (always in the future, always on the shift)
    today = datetime.now(settings.tz).date()
    monday = today + timedelta(days=(7 - today.weekday()) or 7)
    assert run(["book", "--patient-id", "2", "--doctor-id", "2", "--start", f"{monday} 09:00"], settings) == 0
    assert run(["book", "--patient-id", "1", "--doctor-id", "2", "--start", f"{monday} 09:05"], settings) == 1
    assert run(["list-appointments", "--date", str(monday)], settings) == 0

    out = capsys.readouterr()
    assert "Doctor #2 added." in out.out and "VIP patient Lina S." in out.out
    assert "overlaps" in out.err and "Lina S." in out.out


def test_update_keygen_and_build(tmp_path, capsys):
    key = tmp_path / "k.pem"
    src = tmp_path / "content"
    src.mkdir()
    (src / "terms.json").write_text("{}")
    assert run(["update-keygen", "--out", str(key)]) == 0
    assert run(["update-keygen", "--out", str(key)]) == 1  # never overwrite a key
    assert run(["update-build", "--src", str(src), "--version", "1.0", "--base-url", "https://u.example/c",
                "--key", str(key), "--out", str(tmp_path / "out")]) == 0
    assert {p.name for p in (tmp_path / "out").iterdir()} == {"1.0.zip", "manifest.json", "manifest.json.sig"}
