"""目录存储 -dlovew：按目录分别展示磁盘容量，并作为仪表盘小组件。

宿主自带的「存储空间」组件把所有存储按盘去重后累加成一个总量
（DashboardChain().storage()）；本插件反过来，按目录配置里的每个
下载目录 / 媒体库目录分别采样，一行一个目录，可选按物理磁盘合并。
"""
import os
from typing import Any, Dict, List, Optional, Tuple

from app.db.oper.systemconfig import SystemConfigOper
from app.schemas.types import SystemConfigKey
from app.sdk.logging import logger
from app.sdk.plugin import _PluginBase
from app.sdk.utilities import SystemUtils

try:
    from .storage_logic import build_rows, extract_paths, format_size
except ImportError:  # 兼容按顶层模块加载的宿主
    from storage_logic import build_rows, extract_paths, format_size  # type: ignore


class DirectoryStoragedlovew(_PluginBase):
    # 插件元数据
    plugin_name = "目录存储 -dlovew"
    plugin_desc = "按目录分别展示存储总量与已用空间，提供仪表盘小组件。"
    plugin_icon = "directory_storage.png"
    plugin_version = "1.0.0"
    plugin_author = "dlovew"
    author_url = "https://github.com/dlovew"
    plugin_config_prefix = "directorystoragedlovew_"
    plugin_order = 10
    auth_level = 1
    LOG_TAG = "[DirectoryStorage] "

    # 运行态配置
    _enabled = False
    _refresh = 60
    _custom_paths = ""
    _merge_by_disk = False
    _warn_percent = 90
    _critical_percent = 95
    _show_path = True
    _local_only = True

    @staticmethod
    def _to_int(value: Any, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(high, int(value)))
        except (TypeError, ValueError):
            return default

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._refresh = self._to_int(config.get("refresh"), 60, 10, 3600)
        self._custom_paths = str(config.get("custom_paths") or "")
        self._merge_by_disk = bool(config.get("merge_by_disk", False))
        self._warn_percent = self._to_int(config.get("warn_percent"), 90, 1, 100)
        self._critical_percent = self._to_int(config.get("critical_percent"), 95, 1, 100)
        self._show_path = bool(config.get("show_path", True))
        self._local_only = bool(config.get("local_only", True))
        logger.info(
            f"{self.LOG_TAG}插件已加载：启用={self._enabled}，"
            f"刷新={self._refresh}s，按磁盘合并={self._merge_by_disk}"
        )

    def get_state(self) -> bool:
        return bool(self._enabled)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        # 仪表盘由 attrs.refresh 驱动宿主定时重新拉取，无需自建定时任务
        return []

    def stop_service(self):
        return None

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                {'component': 'VSwitch', 'props': {
                                    'model': 'enabled', 'label': '启用插件',
                                    'color': 'primary', 'inset': True}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                {'component': 'VSwitch', 'props': {
                                    'model': 'merge_by_disk', 'label': '按磁盘合并同盘目录',
                                    'color': 'primary', 'inset': True}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                {'component': 'VSwitch', 'props': {
                                    'model': 'show_path', 'label': '显示完整路径',
                                    'color': 'primary', 'inset': True}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                {'component': 'VSwitch', 'props': {
                                    'model': 'local_only', 'label': '仅统计本地存储',
                                    'color': 'primary', 'inset': True}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                {'component': 'VTextField', 'props': {
                                    'model': 'refresh', 'label': '仪表盘刷新间隔（秒）',
                                    'type': 'number'}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                {'component': 'VTextField', 'props': {
                                    'model': 'warn_percent', 'label': '警告阈值（%）',
                                    'type': 'number'}}]},
                            {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [
                                {'component': 'VTextField', 'props': {
                                    'model': 'critical_percent', 'label': '严重阈值（%）',
                                    'type': 'number'}}]},
                            {'component': 'VCol', 'props': {'cols': 12}, 'content': [
                                {'component': 'VTextarea', 'props': {
                                    'model': 'custom_paths',
                                    'label': '补充目录（每行一个）',
                                    'rows': 5,
                                    'placeholder': '卷3|/vol3  或  /vol3',
                                    'hint': '格式：名称|路径，或直接写路径；# 开头为注释。用于展示未配置在「目录」里的卷。',
                                    'persistent-hint': True}}]},
                            {'component': 'VCol', 'props': {'cols': 12}, 'content': [
                                {'component': 'VAlert', 'props': {
                                    'type': 'info', 'variant': 'tonal'},
                                 'text': '在仪表盘「添加组件」里选择「目录存储 · 列表」或「目录存储 · 紧凑」。容量取自目录所在磁盘分区，同一磁盘上的多个目录数字相同，可开启「按磁盘合并」去重。'}]},
                        ],
                    },
                ],
            }
        ], {
            "enabled": self._enabled,
            "refresh": self._refresh,
            "custom_paths": self._custom_paths,
            "merge_by_disk": self._merge_by_disk,
            "warn_percent": self._warn_percent,
            "critical_percent": self._critical_percent,
            "show_path": self._show_path,
            "local_only": self._local_only,
        }

    # ------------------------------------------------------------------
    # 仪表盘
    # ------------------------------------------------------------------
    @staticmethod
    def get_dashboard_meta() -> Optional[List[Dict[str, str]]]:
        return [
            {"key": "list", "name": "目录存储 · 列表"},
            {"key": "compact", "name": "目录存储 · 紧凑"},
        ]

    def get_dashboard(self, key: str = "", **kwargs) -> Optional[Tuple[dict, dict, List[dict]]]:
        if not self._enabled:
            return None
        rows = self.__rows()
        compact = str(key or '') == 'compact'
        cols = {"cols": 12, "md": 4 if compact else 6}
        attrs = {
            "refresh": self._refresh,
            "border": True,
            "title": "存储空间" if compact else "目录存储空间",
            "subtitle": f"共 {len(rows)} 项 · 每 {self._refresh} 秒刷新",
        }
        return cols, attrs, self.__elements(rows, compact=compact)

    def get_page(self) -> List[dict]:
        dashboard = self.get_dashboard(key='list')
        if not dashboard:
            return [{'component': 'div', 'props': {'class': 'text-caption'},
                     'text': '插件未启用，请在设置页开启。'}]
        return dashboard[2]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/usage",
                "endpoint": self.usage_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取各目录容量（只读）",
            }
        ]

    def usage_api(self) -> Dict[str, Any]:
        """返回结构化容量数据，便于排查与二次开发。"""
        return {"rows": self.__rows(), "refresh": self._refresh}

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    @staticmethod
    def __directories() -> List[Any]:
        """读取宿主「目录」配置（TransferDirectoryConf 列表）。"""
        try:
            return SystemConfigOper().get(SystemConfigKey.Directories) or []
        except Exception as err:
            logger.warning(f"{DirectoryStoragedlovew.LOG_TAG}读取目录配置失败：{err}")
            return []

    @staticmethod
    def __disk_key(path: str) -> str:
        """确定路径所在物理磁盘，用于「按磁盘合并」。"""
        try:
            if os.name == 'nt':
                return (os.path.splitdrive(os.path.abspath(path))[0] or 'root').upper()
            return str(os.stat(path).st_dev)
        except Exception:
            return os.path.normpath(path)

    def __usage(self, path: str):
        """返回 (total, free, disk_key)，容量查询失败时返回 0。"""
        try:
            total = float(SystemUtils.total_space(path) or 0)
            free = float(SystemUtils.free_space(path) or 0)
        except Exception as err:
            logger.debug(f"{self.LOG_TAG}读取容量失败 {path}：{err}")
            total = free = 0.0
        return total, free, self.__disk_key(path)

    def __rows(self) -> List[Dict[str, Any]]:
        items = extract_paths(
            self.__directories(),
            custom_paths=self._custom_paths,
            local_only=self._local_only,
        )
        return build_rows(
            items,
            self.__usage,
            merge_by_disk=self._merge_by_disk,
            warn=self._warn_percent,
            critical=self._critical_percent,
        )

    def __elements(self, rows: List[Dict[str, Any]], compact: bool = False) -> List[dict]:
        if not rows:
            return [{
                'component': 'div',
                'props': {'class': 'text-caption text-medium-emphasis'},
                'text': '未获取到可用的本地目录容量，请检查「目录」配置或补充自定义路径。',
            }]
        nodes: List[dict] = []
        for row in rows:
            detail = f"可用 {format_size(row['free'])}　已用 {row['percent']:.1f}%"
            if self._show_path and not compact:
                detail = f"{row['path']}　{detail}"
            nodes.append({
                'component': 'div',
                'props': {'class': 'mb-3'},
                'content': [
                    {
                        'component': 'div',
                        'props': {'style': ('display:flex;justify-content:space-between;'
                                            'align-items:baseline;gap:.5rem')},
                        'content': [
                            {'component': 'div',
                             'props': {'class': 'text-body-2 font-weight-medium',
                                       'style': ('white-space:nowrap;overflow:hidden;'
                                                 'text-overflow:ellipsis')},
                             'text': row['label']},
                            {'component': 'div',
                             'props': {'class': 'text-caption text-medium-emphasis',
                                       'style': 'white-space:nowrap'},
                             'text': f"{format_size(row['used'])} / {format_size(row['total'])}"},
                        ],
                    },
                    {
                        'component': 'div',
                        'props': {'style': ('height:8px;background:rgba(128,128,128,.18);'
                                            'border-radius:4px;overflow:hidden;margin-top:4px')},
                        'content': [{
                            'component': 'div',
                            'props': {'style': (
                                f"width:{min(row['percent'], 100):.1f}%;height:100%;"
                                f"background:{row['color']}")},
                        }],
                    },
                    {'component': 'div',
                     'props': {'class': 'text-caption text-medium-emphasis mt-1',
                               'style': ('white-space:nowrap;overflow:hidden;'
                                         'text-overflow:ellipsis')},
                     'text': detail},
                ],
            })
        return nodes
