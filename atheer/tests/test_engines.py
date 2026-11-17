"""CalcEngine formulary, AutoUpdater hot reload/rollback, and pyttsx3 voice selection."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from atheer.calculations.engine import CalcEngine, UnknownDrugError
from atheer.core.config import Settings
from atheer.updater.publish import build_release, generate_keypair
from atheer.updater.service import AutoUpdater, ContentUpdater, UpdateError
from atheer.updater.terminology import TerminologyStore
from atheer.voice.engines import Pyttsx3TTS

URL = "https://updates.example/manifest.json"


def test_calc_engine_formulary(tmp_path):
    calc = CalcEngine()
    path = tmp_path / "f.json"
    path.write_text(json.dumps([{"drug_name": "Drug A", "min_mg_per_kg": 1, "max_mg_per_kg": 2}]))
    assert calc.load_formulary(path) == 1
    assert calc.verify_dose("  drug   a ", 30, 20).status.value == "within_range"
    with pytest.raises(UnknownDrugError):
        calc.rule("Drug B")

    path.write_text(json.dumps([{"drug_name": "Bad", "min_mg_per_kg": 5, "max_mg_per_kg": 1}]))
    with pytest.raises(ValueError):
        calc.load_formulary(path)
    assert calc.drugs == ["Drug A"]  # invalid file leaves the current formulary intact


def _release(src, version, pem, server):
    bundle_url = f"https://updates.example/{version}.zip"
    bundle, manifest, sig = build_release(src, version, bundle_url, pem)
    server.update({URL: manifest, URL + ".sig": sig, bundle_url: bundle})


def test_auto_updater_hot_reload_and_rollback(tmp_path):
    pem, pub = generate_keypair()
    server: dict[str, bytes] = {}
    src = tmp_path / "src"
    (src / "terminology").mkdir(parents=True)
    (src / "terminology" / "core.json").write_text(json.dumps({"BP": {"ar": "ضغط الدم"}}), encoding="utf-8")
    (src / "formulary.json").write_text(json.dumps([{"drug_name": "X", "min_mg_per_kg": 1, "max_mg_per_kg": 2}]))

    settings = Settings(_env_file=None, content_dir=tmp_path / "content", update_manifest_url=URL)
    updater = AutoUpdater(settings, updater=ContentUpdater(settings.content_dir, pub, fetch=lambda u, _l: server[u]))
    terms, calc = TerminologyStore(), CalcEngine()
    updater.subscribe(terms.load)
    updater.subscribe(lambda rel: calc.load_formulary(rel / "formulary.json"))

    _release(src, "1.0", pem, server)
    assert updater.check_now() == "1.0"
    assert terms.lookup("bp") == {"ar": "ضغط الدم"} and calc.drugs == ["X"]
    assert updater.check_now() is None

    # 2.0 passes signature/JSON checks but the app rejects its formulary → automatic rollback to 1.0.
    (src / "formulary.json").write_text(json.dumps([{"drug_name": "Y", "min_mg_per_kg": 9, "max_mg_per_kg": 1}]))
    _release(src, "2.0", pem, server)
    with pytest.raises(UpdateError, match="rejected"):
        updater.check_now()
    assert updater.current_version == "1.0" and calc.drugs == ["X"]
    assert updater.status()["last_error"]


def test_prune_ignores_unexpected_folders(tmp_path):
    pem, pub = generate_keypair()
    server: dict[str, bytes] = {}
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.json").write_text("{}")
    updater = ContentUpdater(tmp_path / "content", pub, fetch=lambda u, _l: server[u])
    (updater.releases / "notes-backup").mkdir()
    for version in ("1.0", "1.1", "1.2", "1.3"):
        _release(src, version, pem, server)
        updater.check_and_apply(URL)
    names = sorted(p.name for p in updater.releases.iterdir())
    assert names == ["1.1", "1.2", "1.3", "notes-backup"]  # keeps 3 newest; leaves unknown folders alone


def test_auto_updater_requires_key():
    with pytest.raises(UpdateError):
        AutoUpdater(Settings(_env_file=None))


class FakePyttsx3:
    def __init__(self) -> None:
        self.props: dict[str, object] = {}
        self.said: list[tuple[str, object]] = []
        self.voices = [
            SimpleNamespace(id="en-voice", name="Microsoft Zira (English)", languages=[]),
            SimpleNamespace(id="ar-voice", name="Microsoft Naayf", languages=[]),
        ]

    def setProperty(self, key, value):  # noqa: N802 - pyttsx3 API
        self.props[key] = value

    def getProperty(self, key):  # noqa: N802
        return self.voices if key == "voices" else self.props.get(key)

    def say(self, text):
        self.said.append((text, self.props.get("voice")))

    def runAndWait(self):  # noqa: N802
        pass


def test_pyttsx3_picks_voice_per_language():
    fake = FakePyttsx3()
    tts = Pyttsx3TTS(150, engine_factory=lambda: fake)
    assert tts.voices == {"en": "en-voice", "ar": "ar-voice"}
    asyncio.run(tts.speak("مرحبا", "ar"))
    asyncio.run(tts.speak("Hello", "en"))
    assert fake.said == [("مرحبا", "ar-voice"), ("Hello", "en-voice")] and fake.props["rate"] == 150
