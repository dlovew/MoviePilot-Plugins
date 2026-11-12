"""集数标签纯逻辑的单元测试。

``episode_tags.py`` 不依赖 MoviePilot 运行时，按文件路径直接加载即可测试。
"""
from __future__ import annotations

import importlib.util

import pytest

from tests.helpers import REPO_ROOT

MODULE_PATH = REPO_ROOT / "plugins.v3" / "downloadsitetagmoddlovew" / "episode_tags.py"


@pytest.fixture(scope="module")
def logic():
    spec = importlib.util.spec_from_file_location("episode_tags_under_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_episodes(logic):
    assert logic.normalize_episodes([3, 1, 2, 2, "05", None, "x", 0]) == [1, 2, 3, 5]
    assert logic.normalize_episodes(None) == []


def test_parse_episodes_from_title(logic):
    assert logic.parse_episodes_from_title(
        "Some.Show.S01E01.1080p.CR.WEB-DL"
    ) == [1]
    assert logic.parse_episodes_from_title(
        "Some.Show.S01E01-E03.1080p.CR.WEB-DL"
    ) == [1, 2, 3]
    assert logic.parse_episodes_from_title("[某某] EP05 1080p") == [5]
    assert logic.parse_episodes_from_title("第01-02集") == [1, 2]
    assert logic.parse_episodes_from_title("[字幕组] 番剧名 [05] [1080p]") == [5]
    assert logic.parse_episodes_from_title("Movie.2026.2160p") == []


def test_split_runs(logic):
    assert logic.split_runs([1, 2, 3, 5, 7, 8]) == [[1, 2, 3], [5], [7, 8]]


def test_build_episode_tags_default_threshold(logic):
    # 阈值 2：大于 1 集的连续段都合并
    assert logic.build_episode_tags([1, 2]) == ["E01-02"]
    assert logic.build_episode_tags([1, 2, 3]) == ["E01-03"]
    assert logic.build_episode_tags([1]) == ["E01"]
    assert logic.build_episode_tags([1, 2, 3, 7, 8, 9, 10]) == [
        "E01-03", "E07-10"
    ]


def test_build_episode_tags_threshold_and_separator(logic):
    # 阈值 <= 1：完全不合并
    assert logic.build_episode_tags([1, 2, 3], threshold=1) == [
        "E01", "E02", "E03"
    ]
    assert logic.build_episode_tags([1, 2, 3], threshold=0) == [
        "E01", "E02", "E03"
    ]
    # 阈值 3：3 集起合并，2 集仍分别打
    assert logic.build_episode_tags([1, 2, 3], threshold=3) == ["E01-03"]
    assert logic.build_episode_tags([1, 2], threshold=3) == ["E01", "E02"]
    # 前缀与分隔符可配，分隔符可为空
    assert logic.build_episode_tags([1, 2, 3], prefix="EP", separator="~") == [
        "EP01~03"
    ]
    assert logic.build_episode_tags([1, 2, 3], separator="") == ["E0103"]
    assert logic.build_episode_tags([], prefix="EP") == []


def test_is_episode_tag(logic):
    prefixes = logic.known_episode_prefixes("EP", "E")
    for tag in ("E01", "E01-03", "EP05", "EP01~03", "E0103"):
        assert logic.is_episode_tag(tag, prefixes) is True
    for tag in ("站点-UBits", "侦探已死 (2021)", "已整理", "E", "", None):
        assert logic.is_episode_tag(tag, prefixes) is False


def test_episode_format(logic):
    assert logic.episode_format(True, "EP", "3", "~") == {
        "enabled": True, "prefix": "EP", "threshold": 3, "separator": "~"
    }
    # 前缀必填：空值回退到 E；分隔符允许为空
    assert logic.episode_format(prefix="", separator="")["prefix"] == "E"
    assert logic.episode_format(separator="")["separator"] == ""
    assert logic.episode_format(threshold="bad")["threshold"] == 2
