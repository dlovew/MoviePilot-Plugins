"""RSS 候选池纯逻辑的单元测试。

``rss_logic.py`` 不依赖 MoviePilot 运行时，因此按文件路径直接加载即可测试，
无需准备宿主的 app.sdk 环境。
"""
from __future__ import annotations

import datetime
import importlib.util
import re
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
        "platform": platform.upper(),
        "platform_token": platform,
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


def test_detect_platforms_keeps_title_spelling(logic):
    """识别结果必须带标题原文片段，供订阅 include 使用。"""
    hits = logic.detect_platforms(
        "Chitose-kun wa Ramune Bin no Naka 2025 S01E01 1080p MyVideo WEB-DL H264 AAC-UBWEB"
    )
    assert hits == [{"key": "MYVIDEO", "token": "MyVideo"}]

    hits = logic.detect_platforms(
        "Dark Machine the Animation 2026 S01E01 1080p CR WEB-DL H264 AAC-UBWEB"
    )
    assert hits == [{"key": "CR", "token": "CR"}]
    assert logic.detect_platforms("普通标题 某番 E01") == []


def test_short_platform_token_does_not_match_longer_words(logic):
    pattern = logic.platform_pattern("CR")
    assert re.search(pattern, "1080p CR WEB-DL", re.IGNORECASE)
    assert not re.search(pattern, "CRC WS", re.IGNORECASE)
    assert "MyVideo" in logic.platform_pattern("MyVideo")
    assert "\\" not in logic.platform_pattern("Baha")


def test_build_include_uses_title_token(logic):
    """include 必须按标题缩写生成，不能写成全称或归一化大写。"""
    include = logic.build_include("CR")
    assert "CR" in include
    assert "Crunchyroll" not in include
    assert "MYVIDEO" not in include

    assert "MyVideo" in logic.build_include("MyVideo")
    assert "MYVIDEO" not in logic.build_include("MyVideo")
    assert "Baha" in logic.build_include("Baha")
    assert "BAHA" not in logic.build_include("Baha")
    assert "TEAM" in logic.build_include("CR", "TEAM")

    assert logic.build_include("") == ""
    assert logic.build_include("UNKNOWN") == ""


def test_build_tier_rules_from_multiselects(logic):
    rules = logic.build_tier_rules(["IQ", "MyVideo"], ["CR"], ["Baha"], True)
    assert [rule["tier"] for rule in rules] == [1, 2, 3, 4]
    assert rules[1]["platforms"] == ["CR"]
    assert rules[1]["pick"] == "unconditional"
    assert rules[3]["platforms"] == ["*"]

    rules = logic.build_tier_rules([], [], [], False)
    assert rules[1]["pick"] == "smallest_normalized_size"


def test_choose_best_prefers_smallest_in_tier_one(logic):
    candidates = [
        _candidate("Viu", 3.0),
        _candidate("IQ", 1.2),
        _candidate("LINETV", 2.0),
        _candidate("CR", 0.1),
    ]
    winner, reason = logic.choose_best(candidates)
    assert winner["platform_token"] == "IQ"
    assert "等效单集体积最小" in reason


def test_choose_best_cr_is_unconditional_when_tier_one_missing(logic):
    candidates = [_candidate("CR", 9.0), _candidate("Baha", 0.2), _candidate("NF", 0.3)]
    winner, reason = logic.choose_best(candidates)
    assert winner["platform_token"] == "CR"
    assert "无条件优先" in reason


def test_choose_best_falls_back_to_tier_three_and_unknown_platform(logic):
    candidates = [_candidate("Baha", 3.0), _candidate("AMZN", 1.0)]
    winner, _ = logic.choose_best(candidates)
    assert winner["platform_token"] == "AMZN"

    single = [_candidate("SOMEPLATFORM", 1.5)]
    winner, _ = logic.choose_best(single)
    assert winner["platform_token"] == "SOMEPLATFORM"


def test_choose_best_handles_missing_size_and_empty_pool(logic):
    candidates = [
        {"platform": "IQ", "platform_token": "IQ", "normalized_size": None, "title": "unknown-size"},
        _candidate("Viu", 2.0),
    ]
    winner, _ = logic.choose_best(candidates)
    assert winner["platform_token"] == "Viu"
    assert logic.choose_best([])[0] is None


def test_choose_best_respects_custom_multiselect_tiers(logic):
    candidates = [
        _candidate("Baha", 0.1),
        _candidate("MyVideo", 9.0),
    ]
    rules = logic.build_tier_rules(["MyVideo"], [], [], True)
    winner, reason = logic.choose_best(candidates, rules)
    assert winner["platform_token"] == "MyVideo"
    assert "MyVideo" in reason


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


def test_group_type_label(logic):
    assert logic.group_type_label(2) == "绝对集数"
    assert logic.group_type_label(6) == "制作顺序"
    assert logic.group_type_label(None) == "未知类型"
    assert "类型" in logic.group_type_label(99)


def test_summarize_seasons(logic):
    assert logic.summarize_seasons({1: list(range(13))}) == "S01(13集)"
    assert "等 2 季" in logic.summarize_seasons({1: [1], 2: [1]}, limit=1)
    assert logic.summarize_seasons(None) == "无季集信息"


def test_elapsed_text(logic):
    now = datetime.datetime(2026, 11, 4, 12, 0, 0)
    assert logic.elapsed_text(logic.now_text(now - datetime.timedelta(minutes=30)), now) == "30 分钟"
    assert "小时" in logic.elapsed_text(logic.now_text(now - datetime.timedelta(hours=5)), now)
    assert "天" in logic.elapsed_text(logic.now_text(now - datetime.timedelta(days=2)), now)
    assert logic.elapsed_text("bad") == "未知"


def test_estimate_line_width(logic):
    assert logic.estimate_line_width("") == 0
    assert logic.estimate_line_width("中文") == 24
    assert logic.estimate_line_width("abc") == 21
    assert logic.estimate_line_width("\t") == 28


def test_content_page_width(logic):
    assert logic.content_page_width([]) == 480
    short = logic.content_page_width(["S01E01"])
    long = logic.content_page_width(["S01E01", "手动忽略该季，后续不再处理" * 5])
    assert long > short
    assert logic.content_page_width(["x" * 10000]) == 1400
    # 必须预留封面/间距/内外边距，否则最长行末尾会被裁掉
    line = "S01E01-E29　2026-11-05 00:10:22　ignored　手动忽略该季，后续不再处理"
    assert logic.content_page_width([line]) >= logic.estimate_line_width(line) + 198


def test_build_filter_html_and_css(logic):
    html = logic.build_filter_html()
    css = logic.build_filter_css()
    for key, label, _ in logic.HISTORY_FILTERS:
        assert f'id="rss-f-{key}"' in html
        assert label in html
    assert 'id="rss-f-all" checked' in html
    assert 'name="rss-rec-filter"' in html
    assert 'type="checkbox" id="rss-rec-expand"' in html
    assert ':has(#rss-f-failed:checked)' in css
    assert '.rss-rec:not(.rss-rec-failed)' in css
    assert 'display:none !important' in css
    assert 'nth-child(n+11)' in css
    assert ':has(#rss-rec-expand:checked)' in css
    # 「收起」默认必须隐藏，且优先级要高于 .rss-filters label
    assert '.rss-filters label.rss-expand-off{display:none !important;}' in css
    assert 'label.rss-expand-on{display:none !important;}' in css
    assert 'label.rss-expand-off{display:inline-flex !important;' in css


def test_candidate_platform_summary(logic):
    candidates = [
        {"platform_token": "LINETV", "team": "UBWEB"},
        {"platform_token": "Baha", "team": "UBWEB"},
        {"platform_token": "Baha", "team": "UBWEB"},
        {"platform_token": "CR", "team": None},
        {},
    ]
    assert logic.candidate_platform_summary(candidates) == (
        "LINETV-UBWEB、Baha-UBWEB、CR、未知平台"
    )
    assert logic.candidate_platform_summary(candidates, limit=2) == "LINETV-UBWEB、Baha-UBWEB"
    assert logic.candidate_platform_summary([]) == "暂无候选"


def test_candidate_platform_items_marks_unknown(logic):
    candidates = [
        {"platform_token": "LINETV", "team": "UBWEB"},
        {"platform": "UNKNOWN", "team": "UBWEB"},
        {"platform_token": "", "team": ""},
    ]
    items = logic.candidate_platform_items(candidates)
    assert [item["label"] for item in items] == [
        "LINETV-UBWEB", "UNKNOWN-UBWEB", "未知平台"
    ]
    assert [item["unknown"] for item in items] == [False, True, True]


def test_candidate_platform_items_shows_size_and_keeps_smallest(logic):
    gib = 1024 ** 3
    candidates = [
        {"platform_token": "LINETV", "team": "UBWEB",
         "normalized_size": 2 * gib, "title": "LINETV big"},
        {"platform_token": "LINETV", "team": "UBWEB",
         "normalized_size": 1.2 * gib, "title": "LINETV small"},
        {"platform_token": "Baha", "team": "UBWEB",
         "normalized_size": 1.5 * gib, "title": "Baha item"},
        {"platform": "UNKNOWN", "team": "UBWEB",
         "normalized_size": 3 * gib, "title": "Unknown Platform Title"},
    ]
    items = logic.candidate_platform_items(candidates)
    assert [item["label"] for item in items] == [
        "LINETV-UBWEB", "Baha-UBWEB", "UNKNOWN-UBWEB"
    ]
    assert items[0]["size_text"] == "1.20 GiB/集"
    assert items[0]["title"] == "LINETV small"
    assert items[2]["unknown"] is True
    assert items[2]["title"] == "Unknown Platform Title"
    assert logic.candidate_platform_summary(candidates) == (
        "LINETV-UBWEB、Baha-UBWEB、UNKNOWN-UBWEB"
    )


def test_reidentify_platforms_only_touches_unknown(logic):
    candidates = [
        {"platform": "LINETV", "platform_token": "LINETV",
         "title": "已识别 S01E01 1080p ABEMA WEB-DL"},
        {"platform": "UNKNOWN", "platform_token": "",
         "title": "某番 S01E01 1080p ABEMA WEB-DL"},
        {"platform": "UNKNOWN", "platform_token": "",
         "title": "另一番 S01E01 1080p CR WEB-DL"},
    ]
    assert logic.reidentify_platforms(candidates, ["CR", "ABEMA"]) == 2
    assert candidates[0]["platform"] == "LINETV"
    assert candidates[1]["platform"] == "ABEMA"
    assert candidates[1]["platform_token"] == "ABEMA"
    assert candidates[2]["platform_token"] == "CR"
    # 已识别的候选再次刷新不会重复计数或改写
    assert logic.reidentify_platforms(candidates, ["CR", "ABEMA"]) == 0


def test_reidentify_platforms_keeps_unknown_when_no_match(logic):
    candidates = [{"platform": "UNKNOWN", "platform_token": "",
                   "title": "普通标题 S01E01 1080p"}]
    assert logic.reidentify_platforms(candidates, ["CR"]) == 0
    assert candidates[0]["platform"] == "UNKNOWN"
