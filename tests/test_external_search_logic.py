"""Pure-logic regression tests for the M Searcher bridge.

Runs without the app dependencies: Pyrogram and the Backend singletons are
stubbed so the parsing/query/registry functions can be exercised offline.

    python tests/test_external_search_logic.py
    pytest tests/test_external_search_logic.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


#----- Stub pyrogram so the helper module can be imported without the app venv
pyrogram = types.ModuleType("pyrogram")
errors = types.ModuleType("pyrogram.errors")


class FloodWait(Exception):
    def __init__(self, value=0):
        super().__init__(value)
        self.value = value


errors.FloodWait = FloodWait
types_mod = types.ModuleType("pyrogram.types")
types_mod.Message = type("Message", (), {})
pyrogram.errors = errors
pyrogram.types = types_mod
sys.modules["pyrogram"] = pyrogram
sys.modules["pyrogram.errors"] = errors
sys.modules["pyrogram.types"] = types_mod

#----- Stub the Backend package so Backend/__init__.py (motor/db) is not imported
backend_pkg = types.ModuleType("Backend")
backend_pkg.__path__ = [str(REPO / "Backend")]
sys.modules["Backend"] = backend_pkg

botmod = types.ModuleType("Backend.pyrofork.bot")
botmod.Userbot = None
sys.modules["Backend.pyrofork"] = types.ModuleType("Backend.pyrofork")
sys.modules["Backend.pyrofork.bot"] = botmod

settings_mod = types.ModuleType("Backend.helper.settings_manager")


class SettingsManager:
    @staticmethod
    def current():
        return types.SimpleNamespace(
            external_search=True,
            external_bot="M1searcherbot",
            staging_channel="-1001234567890",
            external_timeout=8,
        )


settings_mod.SettingsManager = SettingsManager
sys.modules["Backend.helper.settings_manager"] = settings_mod

logger_mod = types.ModuleType("Backend.logger")
logger_mod.LOGGER = types.SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None)
sys.modules["Backend.logger"] = logger_mod

from Backend.helper import external_search as es  # noqa: E402


def test_query_variants():
    assert es.build_query("House of the Dragon", 2022, 3, 2) == "House of the Dragon S03E02"
    assert es.build_query_variants("House of the Dragon", 2022, 3, 2) == [
        "House of the Dragon S03E02",
        "House of the Dragon S03 EP02",
        "House of the Dragon S03",
        "House of the Dragon",
    ]
    assert es.build_query_variants("Thevar Magan", 1992) == [
        "Thevar Magan 1992",
        "Thevar Magan",
    ]


def test_episode_queries():
    assert es.build_episode_queries("Heart Beat", 1, 1) == [
        "Heart Beat S01E01",
        "Heart Beat S01E1",
        "Heart Beat S01 EP01",
        "Heart Beat S01",
    ]
    assert es.build_episode_queries("House of the Dragon", 3, 2) == [
        "House of the Dragon S03E02",
        "House of the Dragon S03E2",
        "House of the Dragon S03 EP02",
        "House of the Dragon S03",
    ]


def test_label_parsing():
    cases = {
        "《827.11 MB》House of the Dragon 2026 720p S03EP08": ("827.11MB", "720p", 3, 8),
        "《1.87 GB》House of the Dragon 2026 1080p S03EP08": ("1.87GB", "1080p", 3, 8),
        "《1.65 GB》House of the Dragon 2026 \xa0 1080 S03EP06": ("1.65GB", "1080p", 3, 6),
        "[3.52 GB] Swapped 2026 1080p Tam + Tel + Hin + En": ("3.52GB", "1080p", None, None),
        "[513.09 MB] Swapped 2026 Tam + Tel + Hin": ("513.09MB", "", None, None),
        "《1.44 GB》VisionQuest Episode 01 S01E01": ("1.44GB", "", 1, 1),
        "《749.28 MB》Heart Beat The Final Encounter 1080p S01E100": ("749.28MB", "1080p", 1, 100),
    }
    for label, (size, quality, season, episode) in cases.items():
        candidate = es.parse_candidate(label, 0, 0)
        assert candidate is not None, label
        assert candidate.size == size, label
        assert candidate.quality == quality, label
        assert candidate.season == season, label
        assert candidate.episode == episode, label

    assert es.parse_candidate("😍 New Dating BoT 😘", 0, 0) is None
    assert es.parse_candidate("📚 Page 1/3", 0, 0) is None
    assert es.parse_candidate("Next ⏩", 0, 0) is None


def test_episode_filtering():
    ep1 = es.parse_candidate("《1.44 GB》VisionQuest Episode 01 S01E01", 0, 0)
    ep7 = es.parse_candidate("《1.61 GB》VisionQuest 2026 1080p S01EP07", 1, 0)
    ep100 = es.parse_candidate("《749.28 MB》Heart Beat 1080p S01E100", 2, 0)

    selected = es.select_candidates([ep7, ep100, ep1], per_quality=0, max_results=20,
                                    season=1, episode=1)
    assert [c.episode for c in selected] == [1]

    # A season-wide page without the requested episode must not fall back to another one
    assert es.select_candidates([ep7, ep100], per_quality=0, max_results=20,
                                season=1, episode=1) == []


def test_all_sources_per_quality():
    candidates = [
        es.parse_candidate("《1.87 GB》Show 1080p S01E01", 0, 0),
        es.parse_candidate("《1.44 GB》Show 1080p S01E01", 1, 0),
        es.parse_candidate("《900 MB》Show 1080p S01E01", 2, 0),
    ]
    assert len(es.select_candidates(candidates, per_quality=0, max_results=20)) == 3
    assert len(es.select_candidates(candidates, per_quality=1, max_results=20)) == 1


def test_tamil_ranking():
    tamil = es.parse_candidate("《700.76 MB》Show 2026 720p Tamil", 0, 0)
    plain = es.parse_candidate("《1.87 GB》Show 2026 1080p", 1, 0)
    ranked = es.select_candidates([plain, tamil], per_quality=1, tamil_first=True)
    assert ranked[0] is tamil


def test_direct_file_candidate():
    class Media:
        file_name = "[MM] Thevar Magan (1992) 1080p Tamil.mkv"
        file_size = 1909232727

    message = types.SimpleNamespace(
        chat=types.SimpleNamespace(id=-1001234567890),
        id=105963,
        document=Media(),
        video=None,
    )
    candidate = es.candidate_from_file(message)
    assert candidate is not None
    assert candidate.size == "1.78GB"
    assert candidate.quality == "1080p"
    assert candidate.tamil is True
    assert candidate.callback_data == ""
    assert candidate.message_id == 105963


def test_request_registry():
    candidate = es.parse_candidate("《1.87 GB》Show 2026 1080p", 0, 0)
    request_id, request = es.register("tok", candidate, "Show")
    assert es.get_request(request_id, "tok") is request
    assert es.get_request(request_id, "other") is None
    assert es.get_request("missing") is None


if __name__ == "__main__":
    test_query_variants()
    test_episode_queries()
    test_label_parsing()
    test_episode_filtering()
    test_all_sources_per_quality()
    test_tamil_ranking()
    test_direct_file_candidate()
    test_request_registry()
    print("all external_search logic tests passed")
