"""目录存储展示的纯逻辑，不依赖 MoviePilot 运行时，便于单元测试。

宿主自带的仪表盘组件会把所有存储按盘去重后累加成一个总量；这里反过来，
按「目录配置里的每个路径」分别采样容量，并可选把同一物理磁盘的行合并。
"""
import os
from typing import Any, Callable, Dict, List, Optional

_UNITS = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')


def format_size(value: Any) -> str:
    """字节数格式化为易读文本，负数与非法值按 0 处理。"""
    try:
        size = float(value)
    except (TypeError, ValueError):
        return '0 B'
    if size <= 0:
        return '0 B'
    index = 0
    while size >= 1024 and index < len(_UNITS) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {_UNITS[index]}"


def usage_percent(total: Any, free: Any) -> float:
    """已用百分比，钳制在 0~100。"""
    try:
        total_value = float(total)
        free_value = float(free)
    except (TypeError, ValueError):
        return 0.0
    if total_value <= 0:
        return 0.0
    used = max(total_value - min(max(free_value, 0.0), total_value), 0.0)
    return min(max(used / total_value * 100, 0.0), 100.0)


def progress_color(percent: Any, warn: Any = 90, critical: Any = 95) -> str:
    """按使用率返回进度条颜色：正常蓝、警告橙、严重红。"""
    try:
        value = float(percent)
        warn_value = float(warn)
        critical_value = float(critical)
    except (TypeError, ValueError):
        return '#1E88E5'
    if value >= critical_value:
        return '#E53935'
    if value >= warn_value:
        return '#FB8C00'
    return '#1E88E5'


def _field(item: Any, name: str) -> Any:
    """同时兼容 dict 与 pydantic 对象。"""
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def extract_paths(confs: Any, custom_paths: Any = '',
                  include_download: bool = True,
                  include_library: bool = True,
                  local_only: bool = True) -> List[Dict[str, str]]:
    """从目录配置里提取待采样的路径。

    ``confs`` 为 ``SystemConfigKey.Directories`` 的内容（list[dict] 或对象列表）；
    ``custom_paths`` 每行支持 ``名称|路径`` 或纯路径，``#`` 开头为注释。
    返回按路径去重后的 ``[{label, path, kind}]``。
    """
    items: List[Dict[str, str]] = []
    for conf in confs or []:
        name = str(_field(conf, 'name') or '目录')
        storage = str(_field(conf, 'storage') or 'local')
        library_storage = str(_field(conf, 'library_storage') or 'local')
        if include_download:
            path = str(_field(conf, 'download_path') or '').strip()
            if path and (not local_only or storage == 'local'):
                items.append({'label': f"{name} · 下载", 'path': path,
                              'kind': 'download'})
        if include_library:
            path = str(_field(conf, 'library_path') or '').strip()
            if path and (not local_only or library_storage == 'local'):
                items.append({'label': f"{name} · 媒体库", 'path': path,
                              'kind': 'library'})

    for line in str(custom_paths or '').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '|' in line:
            label, path = (part.strip() for part in line.split('|', 1))
        else:
            label, path = line, line
        if path:
            items.append({'label': label or path, 'path': path, 'kind': 'custom'})

    seen = set()
    unique: List[Dict[str, str]] = []
    for item in items:
        key = os.path.normpath(item['path'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def build_rows(items: Any, usage_func: Callable[[str], tuple],
               merge_by_disk: bool = False,
               warn: Any = 90, critical: Any = 95) -> List[Dict[str, Any]]:
    """把路径列表转成展示行。

    ``usage_func(path)`` 返回 ``(total, free, disk_key)``；容量为 0（路径
    不存在或远程存储不可查）的行会被丢弃。``merge_by_disk`` 为真时按
    ``disk_key`` 合并同一物理磁盘的行，并把目录名汇总在一起。
    """
    rows: List[Dict[str, Any]] = []
    for item in items or []:
        path = str(item.get('path') or '')
        if not path:
            continue
        try:
            total, free, disk_key = usage_func(path)
        except Exception:
            continue
        try:
            total = max(float(total or 0), 0.0)
            free = min(max(float(free or 0), 0.0), total)
        except (TypeError, ValueError):
            continue
        if total <= 0:
            continue
        used = max(total - free, 0.0)
        percent = usage_percent(total, free)
        rows.append({
            'label': str(item.get('label') or path),
            'path': path,
            'kind': str(item.get('kind') or 'custom'),
            'disk_key': str(disk_key or path),
            'total': total,
            'used': used,
            'free': free,
            'percent': percent,
            'color': progress_color(percent, warn, critical),
        })

    if merge_by_disk:
        merged: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = row['disk_key']
            if key not in merged:
                merged[key] = dict(row, labels=[row['label']],
                                   paths=[row['path']])
            else:
                merged[key]['labels'].append(row['label'])
                merged[key]['paths'].append(row['path'])
        rows = []
        for row in merged.values():
            row['label'] = ' / '.join(dict.fromkeys(row['labels']))
            row['path'] = '、'.join(dict.fromkeys(row['paths']))
            rows.append(row)
    return rows
