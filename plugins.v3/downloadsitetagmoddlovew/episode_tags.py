"""集数标签的纯逻辑：不依赖宿主运行时，便于单元测试。

标签规则：
- 前缀默认 ``E``，集数固定两位补零，如 ``E01``。
- 连续集数分段，段长「超过」合并阈值时才合并成 ``E01-03``；
  阈值 <= 1 表示完全不合并。
- 合并分隔符可为空（``E0103``）。
"""
import re
from typing import Any, Dict, List, Sequence

# 标题里常见的集数写法，作为 MetaInfo.episode_list 解析失败时的兜底
_TITLE_PATTERNS = (
    re.compile(
        r'(?:E|EP|Ep|ep)\s*(\d{1,4})\s*(?:[-~–—]\s*(?:E|EP|Ep|ep)?\s*(\d{1,4}))?',
        re.IGNORECASE,
    ),
    re.compile(r'第\s*(\d{1,4})\s*(?:[-~–—]\s*(\d{1,4}))?\s*[集话話]'),
)


def normalize_episodes(values: Any) -> List[int]:
    """把任意集数序列规整为去重升序的正整数列表。"""
    result = set()
    for value in values or []:
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if 0 < number <= 9999:
            result.add(number)
    return sorted(result)


def parse_episodes_from_title(title: Any) -> List[int]:
    """从种子标题兜底解析集数；支持 E01、E01-E03、EP01、第01集 等写法。"""
    text = str(title or '')
    numbers: List[int] = []
    for pattern in _TITLE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                start = int(match.group(1))
            except (TypeError, ValueError):
                continue
            end_raw = match.group(2)
            if end_raw:
                try:
                    end = int(end_raw)
                except (TypeError, ValueError):
                    end = start
                # 避免异常标题导致生成上万集
                if start <= end <= start + 200:
                    numbers.extend(range(start, end + 1))
                else:
                    numbers.append(start)
            else:
                numbers.append(start)
    return normalize_episodes(numbers)


def split_runs(episodes: Sequence[int]) -> List[List[int]]:
    """把集数切成连续段，例如 [1,2,3,5,7,8] -> [[1,2,3],[5],[7,8]]。"""
    runs: List[List[int]] = []
    for number in sorted(set(episodes or [])):
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    return runs


def build_episode_tags(episodes: Any, prefix: str = 'E', threshold: Any = 2,
                       separator: Any = '-') -> List[str]:
    """按配置生成集数标签列表。"""
    prefix = str(prefix or '').strip() or 'E'
    sep = '' if separator is None else str(separator)
    try:
        merge_threshold = int(threshold)
    except (TypeError, ValueError):
        merge_threshold = 2
    merge_enabled = merge_threshold > 1

    tags: List[str] = []
    for run in split_runs(normalize_episodes(episodes)):
        if merge_enabled and len(run) > merge_threshold:
            tags.append(f"{prefix}{run[0]:02d}{sep}{run[-1]:02d}")
        else:
            tags.extend(f"{prefix}{number:02d}" for number in run)
    return tags


def is_episode_tag(tag: Any, prefixes: Any) -> bool:
    """判断标签是否属于「旧/新格式集数标签」，用于全量刷新时迁移清理。

    ``prefixes`` 可包含当前前缀、上一次使用的前缀与常见前缀（E/EP）。
    只匹配 ``前缀 + 数字`` 或 ``前缀 + 数字 + 可选分隔符 + 数字``，
    不会误伤站点名、剧名等普通标签。
    """
    text = str(tag or '').strip()
    if not text:
        return False
    escaped = sorted(
        {re.escape(str(item).strip()) for item in (prefixes or []) if str(item).strip()},
        key=len,
        reverse=True,
    )
    if not escaped:
        return False
    pattern = re.compile(
        r'^(?:' + '|'.join(escaped) + r')\d{2,4}(?:[^\w]?\d{2,4})?$',
        re.IGNORECASE,
    )
    return bool(pattern.match(text))


def known_episode_prefixes(current: Any = None, previous: Any = None) -> List[str]:
    """本次刷新需要识别/清理的集数标签前缀集合。"""
    values = ['E', 'EP', str(current or '').strip()]
    if previous:
        values.append(str(previous).strip())
    return sorted({value for value in values if value}, key=len, reverse=True)


def episode_format(enabled: Any = True, prefix: Any = 'E', threshold: Any = 2,
                   separator: Any = '-') -> Dict[str, Any]:
    """归一化的格式配置，用于检测配置变化并触发存量标签刷新。"""
    try:
        merge_threshold = int(threshold)
    except (TypeError, ValueError):
        merge_threshold = 2
    return {
        'enabled': bool(enabled),
        'prefix': str(prefix or '').strip() or 'E',
        'threshold': merge_threshold,
        'separator': '' if separator is None else str(separator),
    }
