"""RSS 候选池纯逻辑的单元测试。

``rss_logic.py`` 不依赖 MoviePilot 运行时，因此按文件路径直接加载即可测试，
无需准备宿主的 app.sdk 环境。
"""
from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest

from tests.helpers import REPO_ROOT

MODULE_PATH = REPO_ROOT / "plugins.v3" / "rsssubscribedlovew" / "rss_logic.py"


@pytest.fixture(scope="module")
def logic():
    spec = importlib.util.spec_from_file_location("rss_logic_under_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate(platform: str, size_per_episode: float, title: str = "") -> dict:
    return {
        "platform": platform,
        "normalized_size": size_per_episode,
        "title": title or platform,
    }


def test_module_is_decoupled_from_host(logic):
    """决策模块不得引入宿主运行时，否则无法独立测试。"""
    source = Path(MODULE_PATH).read_text(encoding="utf-8")
    assert "app.sdk" not in source
    assert "from app." not in source


def test_normalized_size_divides_by_episode_count(logic):
    gib = 1024 ** 3
    assert logic.normalized_size(2 * gib, 2) == gib
    assert logic.normalized_size(3 * gib, 1) == 3 * gib
    assert logic.normalized_size(0, 1) is None
    assert logic.normalized_size("bad", 1) is None
    assert logic.normalized_size(gib, 0) == gib


def test_pool_key_is_stable_and_group_aware(logic):
    assert logic.pool_key("tmdb", "12345", 2) == "tmdb:12345:S02"
    assert logic.pool_key("tmdb", "12345", 2, "group-1") == "tmdb:12345:S02:Ggroup-1"
    assert logic.pool_key("tmdb", "12345", None) == "tmdb:12345:S00"


def test_detect_platforms(logic):
    assert logic.detect_platforms("[IQ] 某番 S01E01 1080p") == ["IQ"]
    assert logic.detect_platforms("MyVideo WEB-DL 某番") == ["MYVIDEO"]
    assert logic.detect_platforms("Crunchyroll 某番") == ["CR"]
    assert logic.detect_platforms("普通标题 某番 E01") == []


def test_choose_best_prefers_smallest_in_tier_one(logic):
    candidates = [
        _candidate("VIU", 3.0),
        _candidate("IQ", 1.2),
        _candidate("LINETV", 2.0),
        _candidate("CR", 0.1),
    ]
    winner, reason = logic.choose_best(candidates)
    assert winner["platform"] == "IQ"
    assert "等效单集体积最小" in reason


def test_choose_best_cr_is_unconditional_when_tier_one_missing(logic):
    candidates = [_candidate("CR", 9.0), _candidate("BAHA", 0.2), _candidate("NF", 0.3)]
    winner, reason = logic.choose_best(candidates)
    assert winner["platform"] == "CR"
    assert "无条件优先" in reason


def test_choose_best_falls_back_to_tier_three_and_unknown_platform(logic):
    candidates = [_candidate("BAHA", 3.0), _candidate("AMZN", 1.0)]
    winner, _ = logic.choose_best(candidates)
    assert winner["platform"] == "AMZN"

    single = [_candidate("SOMEPLATFORM", 1.5)]
    winner, _ = logic.choose_best(single)
    assert winner["platform"] == "SOMEPLATFORM"


def test_choose_best_handles_missing_size_and_empty_pool(logic):
    candidates = [
        {"platform": "IQ", "normalized_size": None, "title": "unknown-size"},
        _candidate("VIU", 2.0),
    ]
    winner, _ = logic.choose_best(candidates)
    assert winner["platform"] == "VIU"
    assert logic.choose_best([])[0] is None


def test_custom_tier_rules_are_honored(logic):
    rules = [{"tier": 1, "platforms": ["VIU"], "pick": "smallest_normalized_size"}]
    winner, _ = logic.choose_best([_candidate("IQ", 0.1), _candidate("VIU", 5.0)], rules)
    assert winner["platform"] == "VIU"


def test_season_matches(logic):
    seasons = {1: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]}
    assert logic.season_matches(seasons, 1, [1]) == "match"
    # 资源按剧集组编号 S02E01，TMDB 主季只有 S01
    assert logic.season_matches(seasons, 2, [1]) == "mismatch"
    assert logic.season_matches({}, 1, [1]) == "unknown"
    assert logic.season_matches({1: 12}, 1, [1, 2]) == "match"
    assert logic.season_matches({1: 12}, 1, [13]) == "mismatch"


def test_is_due_starts_from_first_seen(logic):
    now = datetime.datetime(2026, 11, 4, 12, 0, 0)
    first_seen = logic.now_text(now - datetime.timedelta(hours=23))
    assert not logic.is_due(first_seen, 24, now)
    assert logic.is_due(first_seen, 24, now + datetime.timedelta(hours=1))
    assert logic.is_due(logic.now_text(now - datetime.timedelta(hours=25)), 24, now)
    assert not logic.is_due("not-a-time", 24, now)


def test_parse_json_config_falls_back(logic):
    default = {"A": "x"}
    assert logic.parse_json_config("", default) is default
    assert logic.parse_json_config("{bad json", default) is default
    assert logic.parse_json_config('{"A": "y"}', default) == {"A": "y"}


def test_trim_records_limits_and_orders(logic):
    records = [
        {"time": "2026-01-01 00:00:00"},
        {"time": "2026-01-03 00:00:00"},
        {"time": "2026-01-02 00:00:00"},
    ]
    trimmed = logic.trim_records(records, 2)
    assert [item["time"] for item in trimmed] == [
        "2026-01-03 00:00:00",
        "2026-01-02 00:00:00",
    ]
