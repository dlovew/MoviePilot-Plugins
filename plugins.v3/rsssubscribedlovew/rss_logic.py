"""RSS 候选池的决策逻辑（纯 Python，不依赖 MoviePilot 运行时）。

抽成独立模块是为了能在仓库内直接做单元测试：宿主侧只负责拉取 RSS、
识别媒体、调用订阅链，所有「谁入池 / 何时结算 / 选哪个平台」的判断都在这里。

平台词条的 key 一律使用资源标题里的实际缩写（如 ``CR`` / ``MyVideo`` /
``Baha``），识别与生成订阅 include 共用同一份词表，避免归一化后写进 include
导致订阅搜不到资源。
"""
from __future__ import annotations

import datetime
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 平台词表：既是识别关键字，也是设置页下拉选项
DEFAULT_PLATFORM_TOKENS: List[str] = [
    "IQ", "LINETV", "MyVideo", "Viu", "CR", "Baha", "NF", "AMZN",
]

# 三个多选框的默认值
DEFAULT_TIER1_PLATFORMS: List[str] = ["IQ", "LINETV", "MyVideo", "Viu"]
DEFAULT_TIER2_PLATFORMS: List[str] = ["CR"]
DEFAULT_TIER3_PLATFORMS: List[str] = ["Baha", "NF", "AMZN"]

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


def platform_pattern(token: Any) -> str:
    """生成平台词条的正则片段。

    短缩写（如 ``CR`` / ``NF``）加前后「非字母数字」边界，避免命中 ``CRC``
    之类的无关片段；长词条直接按原文匹配，保留标题里的大小写与空格写法。
    """
    text = str(token or '').strip()
    if not text:
        return ''
    escaped = re.escape(text)
    if len(text) <= 3:
        return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    return escaped


def detect_platforms(title: str, tokens: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """按词表顺序返回命中的平台。

    每项包含 ``key``（归一化大写，仅供分层匹配）与 ``token``（标题里
    实际抠出来的原文片段，用于生成订阅 include）。
    """
    rules = tokens if tokens is not None else DEFAULT_PLATFORM_TOKENS
    hits: List[Dict[str, str]] = []
    for token in rules:
        expression = platform_pattern(token)
        if not expression:
            continue
        match = re.search(expression, str(title or ''), re.IGNORECASE)
        if match:
            hits.append({'key': str(token).upper(), 'token': match.group(0)})
    return hits


def build_include(platform_token: Any, team: Any = None) -> str:
    """用标题原文平台片段构造订阅 include 正则；未识别平台时不加平台条件。"""
    parts = []
    token = str(platform_token or '').strip()
    if token and token.upper() != 'UNKNOWN':
        parts.append(f"(?=.*{platform_pattern(token)})")
    if team:
        parts.append(f"(?=.*{re.escape(str(team))})")
    return "".join(parts)


def build_tier_rules(tier1: Optional[List[str]], tier2: Optional[List[str]],
                     tier3: Optional[List[str]],
                     tier2_unconditional: bool = True) -> List[Dict[str, Any]]:
    """把设置页的三个多选框转换为分层选优规则；末层兜底任何已识别平台。"""
    return [
        {"tier": 1, "platforms": list(tier1 or []), "pick": "smallest_normalized_size"},
        {
            "tier": 2,
            "platforms": list(tier2 or []),
            "pick": "unconditional" if tier2_unconditional else "smallest_normalized_size",
        },
        {"tier": 3, "platforms": list(tier3 or []), "pick": "smallest_normalized_size"},
        {"tier": 4, "platforms": ["*"], "pick": "smallest_normalized_size"},
    ]


def parse_json_config(text: Any, fallback: Any) -> Any:
    """解析可选的 JSON 文本框，填错时静默回退到默认值。"""
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
    - 分层匹配用归一化 ``key``，展示与订阅用标题原文 ``token``。
    """
    items = list(candidates or [])
    if not items:
        return None, "候选池为空"
    rules = tier_rules or build_tier_rules(
        DEFAULT_TIER1_PLATFORMS, DEFAULT_TIER2_PLATFORMS, DEFAULT_TIER3_PLATFORMS
    )
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
        label = winner.get('platform_token') or winner.get('platform')
        size = winner.get("normalized_size")
        size_text = f"{size / 1024 ** 3:.2f} GiB/集" if isinstance(size, (int, float)) else "体积未知"
        if rule.get("pick") == "unconditional":
            return winner, f"Tier{tier} 无条件优先 {label}（{size_text}）"
        return winner, f"Tier{tier} 等效单集体积最小：{label}（{size_text}）"
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


GROUP_TYPE_LABELS = {
    1: "首播顺序",
    2: "绝对集数",
    3: "DVD",
    4: "数字发行",
    5: "故事线",
    6: "制作顺序",
    7: "电视",
}


def group_type_label(value: Any) -> str:
    """TMDB 剧集组类型转成可读标签；未知类型原样显示。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value or "未知类型")
    return GROUP_TYPE_LABELS.get(number, f"类型 {number}")


def summarize_seasons(seasons: Any, limit: int = 3) -> str:
    """把 TMDB 主季集信息压成 ``S01(13集)`` 形式的短文本，便于数据页展示。"""
    if not isinstance(seasons, dict) or not seasons:
        return "无季集信息"
    parts = []
    for number, episodes in list(seasons.items())[:max(limit, 1)]:
        try:
            count = int(episodes)
        except (TypeError, ValueError):
            count = len(episodes) if isinstance(episodes, (list, tuple, set)) else 0
        if str(number).isdigit():
            parts.append(f"S{int(number):02d}({count}集)")
        else:
            parts.append(f"{number}({count}集)")
    if len(seasons) > len(parts):
        parts.append(f"等 {len(seasons)} 季")
    return "、".join(parts)


def elapsed_text(first_seen: Any, now: Optional[datetime.datetime] = None) -> str:
    """入池后已等待多久，用于数据页挂起条目。"""
    started = parse_timestamp(first_seen)
    if started is None:
        return "未知"
    current = (now or datetime.datetime.now()).replace(tzinfo=None)
    seconds = max((current - started).total_seconds(), 0)
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} 小时"
    return f"{seconds / 86400:.1f} 天"


def candidate_platform_items(candidates: Any, limit: int = 8) -> List[Dict[str, Any]]:
    """按「平台-制作组」归并候选，附带等效体积与原始标题。

    同一标签保留等效单集体积最小的那条（与结算选优一致）；未识别平台标记
    ``unknown`` 并带上原始 RSS 标题，便于复制标题里的缩写补充平台词表。
    """
    grouped: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        platform = str(candidate.get('platform_token')
                       or candidate.get('platform') or '').strip()
        team = str(candidate.get('team') or '').strip()
        unknown = platform.upper() in ('', 'UNKNOWN')
        label = f"{platform}-{team}" if platform and team else (platform or team or '未知平台')
        size = candidate.get('normalized_size')
        size_value = float(size) if isinstance(size, (int, float)) else None
        size_text = (f"{size_value / 1024 ** 3:.2f} GiB/集"
                     if size_value is not None else '体积未知')
        record = {
            'label': label,
            'unknown': unknown,
            'size_text': size_text,
            'title': str(candidate.get('title') or ''),
            '_size': size_value,
        }
        existing = grouped.get(label)
        if existing is None:
            grouped[label] = record
        elif record['_size'] is not None and (
                existing['_size'] is None or record['_size'] < existing['_size']):
            grouped[label] = record
    items = []
    for record in list(grouped.values())[:max(limit, 1)]:
        items.append({key: value for key, value in record.items() if key != '_size'})
    return items


def candidate_platform_summary(candidates: Any, limit: int = 8) -> str:
    """把候选资源压成一行「平台-制作组」清单，保持数据页简洁。"""
    return '、'.join(item['label'] for item in candidate_platform_items(candidates, limit)) or '暂无候选'


def reidentify_platforms(candidates: Any,
                         tokens: Optional[List[str]] = None) -> int:
    """只按当前词表重新识别「未识别平台」的候选，原地更新并返回刷新条数。

    已识别出平台的候选一律不动；只有命中新词表才改写，避免把 UNKNOWN
    换成更差的结果。用于用户补充自定义平台缩写后的手动刷新。
    """
    rules = tokens if tokens is not None else DEFAULT_PLATFORM_TOKENS
    refreshed = 0
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        platform = str(candidate.get('platform') or '').upper()
        if platform and platform != 'UNKNOWN' and candidate.get('platform_token'):
            continue
        hits = detect_platforms(candidate.get('title') or '', rules)
        if not hits:
            continue
        candidate['platform'] = hits[0]['key']
        candidate['platform_token'] = hits[0]['token']
        candidate['platform_hits'] = [hit['token'] for hit in hits]
        refreshed += 1
    return refreshed
