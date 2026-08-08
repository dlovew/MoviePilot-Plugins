"""
qbtorrentfixer - 修复 qBittorrent 中"混合"状态的订阅合集种子

问题背景：
    通过 MoviePilot 订阅某剧集时，若最后一集以"打包合集"形式发布（含 1~N 集），
    MoviePilot 会拆包并只勾选合集中的最后一集下载。这会导致 qBittorrent 中该种子
    处于"混合"状态（部分文件下载、部分文件 priority=0）。
    本插件定时扫描 qBittorrent 中所有"混合"状态的种子，将其全部文件优先级恢复为
    正常（priority=1），从而把种子状态由"混合"改回"正常"。
"""

import re
from typing import Any, Dict, List, Tuple

from apscheduler.triggers.cron import CronTrigger

from app.core.event import eventmanager, Event
from app.helper.downloader import DownloaderHelper
from app.plugins import _PluginBase
from app.schemas.types import EventType


class QbTorrentFixer(_PluginBase):
    # 插件在界面中的展示名称
    plugin_name = "qBittorrent 混合种子修复"
    # 插件描述
    plugin_desc = (
        "定时扫描 qBittorrent 中因 MoviePilot 拆包只下载合集最后一集"
        "而处于混合状态的种子，将其全部文件优先级恢复为正常。"
    )
    # 插件图标
    plugin_icon = "qBittorrent_A.png"
    # 插件版本，必须和 package.v2.json 中保持一致
    plugin_version = "1.0.3"
    # 作者信息
    plugin_author = "dlovew"
    author_url = "https://github.com/dlovew"
    # 配置项前缀，保持唯一
    plugin_config_prefix = "qbtorrentfixer_"
    # 插件加载顺序
    plugin_order = 50
    # 插件可见权限级别
    auth_level = 1

    # 运行时状态字段
    _enabled = False
    _cron = "0 * * * *"
    _only_tag = ""
    _only_tracker = ""
    _notify_only = False
    _notify = True
    _message = "插件尚未初始化"

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._cron = config.get("cron") or "0 * * * *"
        self._only_tag = (config.get("only_tag") or "").strip()
        self._only_tracker = (config.get("only_tracker") or "").strip()
        self._notify_only = bool(config.get("notify_only"))
        self._notify = config.get("notify", True)
        self._message = "插件已初始化"

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {
                "cmd": "/qbtorrentfixer_run",
                "event": EventType.PluginAction,
                "desc": "立即修复 qB 混合状态种子",
                "category": "插件命令",
                "data": {"action": "qbtorrentfixer_run"},
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if not self.get_state():
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except Exception as e:  # noqa: BLE001
            self.error(f"定时表达式无效：{str(e)}，已回退为每小时执行")
            trigger = CronTrigger.from_crontab("0 * * * *")
        return [
            {
                "id": "QbTorrentFixer.Scan",
                "name": "qB 混合种子修复定时扫描",
                "trigger": trigger,
                "func": self.scan_and_fix,
                "kwargs": {},
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify_only",
                                            "label": "仅通知不处理（只报告不修改）",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify",
                                            "label": "处理后发送通知",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VBtn",
                                        "props": {
                                            "color": "primary",
                                            "variant": "tonal",
                                            "onclick": "/qbtorrentfixer_run",
                                            "text": "立即运行一次",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 9},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "variant": "tonal",
                                            "text": "「立即运行一次」将按当前配置（含「仅通知不处理」开关）"
                                                    "手动触发一次扫描，不影响定时任务的执行。",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cron",
                                            "label": "定时扫描表达式（cron）",
                                            "placeholder": "0 * * * *",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "only_tag",
                                            "label": "仅处理带以下标签的种子（留空=不过滤）",
                                            "placeholder": "moviepilot",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "only_tracker",
                                            "label": "仅处理特定站点（tracker 域名，留空=全部）",
                                            "placeholder": "example.com,tracker.net",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "本插件会扫描所有已启用的 qBittorrent 下载器，"
                                                    "将处于「混合」状态（部分文件未选中）的种子全部文件"
                                                    "优先级恢复为正常，从而把状态由混合改回正常。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "cron": "0 * * * *",
            "only_tag": "",
            "only_tracker": "",
            "notify_only": False,
            "notify": True,
        }

    def get_page(self) -> List[dict]:
        return [
            {
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "text": self._message,
                },
            }
        ]

    @eventmanager.register(EventType.PluginAction)
    def run_command(self, event: Event):
        event_data = event.event_data or {}
        # 兼容不同 MP 版本对 onclick 命令的 action 派发（带/不带斜杠）
        action = str(event_data.get("action") or "").lstrip("/")
        if action != "qbtorrentfixer_run":
            return
        self.scan_and_fix()

    # ------------------------------------------------------------------ #
    # 核心逻辑
    # ------------------------------------------------------------------ #
    def scan_and_fix(self):
        """扫描所有 qBittorrent 下载器，修复混合状态种子。"""
        if not self.get_state():
            return

        helper = DownloaderHelper()
        services = helper.get_services() or []
        qb_services = [s for s in services if s.type == "qbittorrent"]

        if not qb_services:
            self.info("未找到已启用的 qBittorrent 下载器，跳过本次扫描。")
            return

        target_tags = {t.strip().lower() for t in self._only_tag.split(",") if t.strip()}
        target_trackers = [t.strip().lower() for t in self._only_tracker.split(",") if t.strip()]
        total_fixed = 0
        total_skipped = 0
        report_lines: List[str] = []

        for service in qb_services:
            downloader = service.instance
            name = service.name
            try:
                torrents = downloader.get_torrents() or []
            except Exception as e:  # noqa: BLE001
                self.error(f"读取下载器 {name} 种子列表失败：{str(e)}")
                continue

            for torrent in torrents:
                # 标签过滤
                if target_tags:
                    tags = {str(t).lower() for t in (torrent.tags or [])}
                    if not (target_tags & tags):
                        continue

                # 站点过滤：取种子所有 tracker 的域名进行匹配
                if target_trackers:
                    trackers = torrent.trackers or []
                    domains = set()
                    for tr in trackers:
                        url = tr.get("url") if isinstance(tr, dict) else str(tr)
                        if url:
                            m = re.search(r"https?://([^/]+)/?", url, re.IGNORECASE)
                            if m:
                                domains.add(m.group(1).lower())
                    if not any(tk in d for d in domains for tk in target_trackers):
                        continue

                # 判定是否为「混合」状态：存在未选中的文件（priority == 0）
                try:
                    files = downloader.get_files(torrent.hash) or []
                except Exception as e:  # noqa: BLE001
                    self.error(f"读取种子 {torrent.name} 文件列表失败：{str(e)}")
                    continue

                if not files:
                    continue

                mixed_file_ids = [
                    f.get("id") for f in files
                    if int(f.get("priority", 1) or 1) == 0
                ]

                if not mixed_file_ids:
                    # 全部文件都在下载，属于正常状态
                    continue

                total_skipped += 1
                line = f"[{name}] {torrent.name}（{len(mixed_file_ids)}/{len(files)} 个文件被取消）"
                report_lines.append(line)
                self.info(f"发现混合状态种子：{line}")

                if self._notify_only:
                    # 仅通知不处理：跳过实际修改
                    continue

                try:
                    # 将全部文件优先级恢复为 1（正常），即把混合状态改为正常
                    all_ids = [f.get("id") for f in files]
                    downloader.set_file_priority(torrent.hash, all_ids, 1)
                    total_fixed += 1
                    self.info(f"已修复种子：{torrent.name}")
                except Exception as e:  # noqa: BLE001
                    self.error(f"修复种子 {torrent.name} 失败：{str(e)}")

        summary = (f"qB 混合种子修复完成：扫描 {len(qb_services)} 个下载器，"
                   f"发现 {total_skipped} 个混合种子，"
                   f"{'仅通知不处理' if self._notify_only else f'已修复 {total_fixed} 个'}。")
        self._message = summary
        self.info(summary)

        if self._notify and report_lines:
            detail = "\n".join(report_lines)
            self.post_message(
                title="qBittorrent 混合种子修复",
                message=f"{summary}\n\n{detail}",
            )
        elif self._notify:
            self.post_message(
                title="qBittorrent 混合种子修复",
                message=summary,
            )

    def stop_service(self):
        pass
