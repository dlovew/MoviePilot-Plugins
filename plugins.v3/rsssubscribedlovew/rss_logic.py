"""RSS 候选池的决策逻辑（纯 Python，不依赖 MoviePilot 运行时）。

抽成独立模块是为了能在仓库内直接做单元测试：宿主侧只负责拉取 RSS、
识别媒体、调用订阅链，所有「谁入池 / 何时结算 / 选哪个平台」的判断都在这里。
"""
from __future__ import annotations

import datetime
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 分层规则：按顺序命中，命中即停止。最后一个 "*" 兜底任何已识别平台。
DEFAULT_TIER_RULES: List[Dict[str, Any]] = [
    {"tier": 1, "platforms": ["IQ", "LINETV", "MYVIDEO", "VIU"], "pick": "smallest_normalized_size"},
    {"tier": 2, "platforms": ["CR"], "pick": "unconditional"},
    {"tier": 3, "platforms": ["BAHA", "NF", "AMZN"], "pick": "smallest_normalized_size"},
    {"tier": 4, "platforms": ["*"], "pick": "smallest_normalized_size"},
]

# 平台识别正则，设置页可用 JSON 覆盖
DEFAULT_PLATFORM_PATTERNS: Dict[str, str] = {
    "IQ": r"\bIQ\b|IQIYI|爱奇艺",
    "LINETV": r"LINETV|LINE[\s._-]?TV",
    "MYVIDEO": r"MY[\s._-]?VIDEO",
    "VIU": r"\bVIU\b",
    "CR": r"\bCR\b|CRUNCHYROLL",
    "BAHA": r"BAHA|BAHAMUT|巴哈",
    "NF": r"\bNF\b|NETFLIX",
    "AMZN": r"\bAMZN\b|AMAZON|\bAMZ\b",
}

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_text(value: Optional[datetime.datetime] = None) -> str:
    """统一使用无时区的本地时间字符串，避免序列化后比较出错。"""
    return (value or datetime.datetime.now()).strftime(TIME_FORMAT)


def parse_timestamp(value: Any) -> Optional[datetime.datetime]:
    """把持久化里的时间还原成 datetime，兼容 datetime 对象与脏数据。"""
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    try:
        return datetime.datetime.strptime(str(value), TIME_FORMAT)
    except (TypeError, ValueError):
        return None


def normalized_size(size: Any, episode_count: Any) -> Optional[float]:
    """等效单集体积（字节）。

    体积只用于在同一季的多个平台版本之间挑选代表，种子本身不下载，
    因此按集数摊平是安全的。体积缺失或非法时返回 None（排序时排最后）。
    """
    try:
        value = float(size)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    try:
        count = int(episode_count)
    except (TypeError, ValueError):
        count = 1
    if count < 1:
        count = 1
    return value / count


def pool_key(media_source: Any, media_id: Any, season: Any,
             episode_group: Any = None) -> str:
    """候选池唯一键：媒体身份 + 资源侧季；使用剧集组时再带上组 ID。"""
    try:
        season_number = int(season)
    except (TypeError, ValueError):
        season_number = 0
    key = f"{media_source or 'unknown'}:{media_id or 'unknown'}:S{season_number:02d}"
    if episode_group:
        key = f"{key}:G{episode_group}"
    return key


def detect_platforms(title: str, patterns: Optional[Dict[str, str]] = None) -> List[str]:
    """按配置顺序返回标题命中的平台名；未命中返回空列表。"""
    rules = patterns or DEFAULT_PLATFORM_PATTERNS
    text = str(title or "").upper()
    hits: List[str] = []
    for platform, expression in rules.items():
        try:
            if re.search(expression, text, re.IGNORECASE):
                hits.append(str(platform).upper())
        except re.error:
            continue
    return hits


def parse_json_config(text: Any, fallback: Any) -> Any:
    """解析设置页里的 JSON 文本框，填错时静默回退到默认值。"""
    if not text or not str(text).strip():
        return fallback
    try:
        parsed = json.loads(str(text))
    except (TypeError, ValueError):
        return fallback
    if isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    if isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    return parsed


def rank_by_size(candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """等效体积升序；体积未知的排最后，其余用平台与标题稳定排序。"""
    return sorted(
        candidates,
        key=lambda item: (
            item.get("normalized_size") is None,
            item.get("normalized_size")
            if isinstance(item.get("normalized_size"), (int, float))
            else float("inf"),
            str(item.get("platform") or ""),
            str(item.get("title") or ""),
        ),
    )


def choose_best(candidates: Sequence[Dict[str, Any]],
                tier_rules: Optional[List[Dict[str, Any]]] = None
                ) -> Tuple[Optional[Dict[str, Any]], str]:
    """分层选优：返回 (选中的候选, 人类可读的理由)。

    - Tier 内的 ``unconditional`` 表示相对其他档无条件优先，组内仍按体积排。
    - 单平台兜底由最后一个 ``"*"`` 规则承担。
    """
    items = list(candidates or [])
    if not items:
        return None, "候选池为空"
    rules = tier_rules or DEFAULT_TIER_RULES
    for rule in rules:
        platforms = [str(p).upper() for p in (rule.get("platforms") or [])]
        if not platforms:
            continue
        if "*" in platforms:
            picked = items
        else:
            wanted = set(platforms)
            picked = [c for c in items
                      if str(c.get("platform") or "").upper() in wanted]
        if not picked:
            continue
        tier = rule.get("tier", "?")
        winner = rank_by_size(picked)[0]
        size = winner.get("normalized_size")
        size_text = f"{size / 1024 ** 3:.2f} GiB/集" if isinstance(size, (int, float)) else "体积未知"
        if rule.get("pick") == "unconditional":
            return winner, f"Tier{tier} 无条件优先 {winner.get('platform')}（{size_text}）"
        return winner, f"Tier{tier} 等效单集体积最小：{winner.get('platform')}（{size_text}）"
    return None, "无平台命中任何分层规则"


def season_matches(mediainfo_seasons: Any, season: Any,
                   episodes: Any) -> str:
    """比对资源侧季集与 TMDB 主季集。

    返回 ``match`` / ``mismatch`` / ``unknown``。``unknown`` 表示 TMDB
    暂时没有可用的集数信息，交由调用方决定重试或按主季订阅。
    """
    if season is None or not isinstance(mediainfo_seasons, dict) or not mediainfo_seasons:
        return "unknown"
    raw = mediainfo_seasons.get(season)
    if raw is None:
        raw = mediainfo_seasons.get(str(season))
    if raw is None:
        return "mismatch"

    available = set()
    try:
        count = int(raw)
        available = set(range(1, count + 1))
    except (TypeError, ValueError):
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                try:
                    available.add(int(item))
                except (TypeError, ValueError):
                    episode_number = getattr(item, "episode_number", None)
                    if episode_number is not None:
                        try:
                            available.add(int(episode_number))
                        except (TypeError, ValueError):
                            continue
            if not available:
                available = set(range(1, len(raw) + 1))
    if not available:
        return "unknown"
    if not episodes:
        return "match"
    try:
        wanted = {int(episode) for episode in episodes}
    except (TypeError, ValueError):
        return "unknown"
    return "match" if wanted.issubset(available) else "mismatch"


def is_due(first_seen: Any, window_hours: Any,
           now: Optional[datetime.datetime] = None) -> bool:
    """窗口是否到期；计时起点是该键第一条入池候选的时间。"""
    started = parse_timestamp(first_seen)
    if started is None:
        return False
    try:
        hours = float(window_hours)
    except (TypeError, ValueError):
        hours = 24.0
    current = (now or datetime.datetime.now()).replace(tzinfo=None)
    return (current - started).total_seconds() >= hours * 3600


def trim_records(records: Sequence[Dict[str, Any]], limit: int = 200) -> List[Dict[str, Any]]:
    """按时间倒序裁剪历史/重试列表，避免持久化无限增长。"""
    items = list(records or [])
    ordered = sorted(items, key=lambda item: str(item.get("time") or ""), reverse=True)
    try:
        size = int(limit)
    except (TypeError, ValueError):
        size = 200
    return ordered[:max(size, 1)]
