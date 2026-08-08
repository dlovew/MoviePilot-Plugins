from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Dict, List, Tuple

import pytz
import re
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.helper.downloader import DownloaderHelper
from app.log import logger
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
    plugin_version = "1.0.2"
    # 作者信息
    plugin_author = "dlovew"
    author_url = "https://github.com/dlovew"
    # 配置项前缀，保持唯一
    plugin_config_prefix = "qbtorrentfixer_"
    # 插件加载顺序
    plugin_order = 50
    # 插件可见权限级别
    auth_level = 1

    # 定时服务 id
    _service_id = "QbTorrentFixer.Scan"
    # 临时调度器（「立即运行一次」使用）
    _scheduler = None
    # 线程锁
    _lock = None

    # 配置项
    _enabled = False
    _cron = "0 * * * *"
    _only_tag = ""
    _only_tracker = ""
    _notify_only = False
    _notify = True
    _onlyonce = False
    # 运行日志
    _message = "插件尚未初始化"
    _last_log: List[str] = []

    def init_plugin(self, config: dict = None):
        self.stop_service()
        self._lock = RLock()
        config = config or {}
        self._enabled = config.get("enabled") or False
        self._cron = config.get("cron") or "0 * * * *"
        self._only_tag = config.get("only_tag") or ""
        self._only_tracker = config.get("only_tracker") or ""
        self._notify_only = config.get("notify_only") or False
        self._notify = config.get("notify", True)
        self._onlyonce = config.get("onlyonce") or False
        self._message = "插件已初始化，尚未运行过扫描。"
        self._last_log = []

        # 「立即运行一次」：开关打开并保存后，延迟 3 秒触发一次扫描，随后把开关复位
        if self._onlyonce:
            logger.info("检测到「立即运行一次」，将延迟触发一次扫描")
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.scan_and_fix,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
            )
            self._scheduler.start()
            self._onlyonce = False
            self.update_config({
                "enabled": self._enabled,
                "cron": self._cron,
                "only_tag": self._only_tag,
                "only_tracker": self._only_tracker,
                "notify_only": self._notify_only,
                "notify": self._notify,
                "onlyonce": False,
            })

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
            logger.error(f"定时表达式无效：{str(e)}，已回退为每小时执行")
            trigger = CronTrigger.from_crontab("0 * * * *")
        return [
            {
                "id": self._service_id,
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
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次（保存配置后触发，运行完自动关闭）",
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
            "onlyonce": False,
        }

    def get_page(self) -> List[dict]:
        # 「数据」标签页：展示最近一次运行日志
        log_text = self._message
        if self._last_log:
            log_text = "\n".join(self._last_log)
        return [
            {
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "style": "white-space: pre-wrap; font-family: monospace;",
                    "text": log_text,
                },
            },
        ]

    def stop_service(self):
        """
        清理「立即运行一次」用到的临时调度器（基类要求的抽象方法）
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                self._scheduler.shutdown(wait=False)
                self._scheduler = None
        except Exception:  # noqa: BLE001
            pass

    @eventmanager.register(EventType.PluginAction)
    def run_command(self, event: Event):
        # 供远程命令（微信/API）调用
        event_data = event.event_data or {}
        action = str(event_data.get("action") or "").lstrip("/")
        if action != "qbtorrentfixer_run":
            return
        self.scan_and_fix()

    # ------------------------------------------------------------------ #
    # 核心逻辑
    # ------------------------------------------------------------------ #
    def scan_and_fix(self):
        """扫描所有 qBittorrent 下载器，修复混合状态种子。"""
        with self._lock:
            logs: List[str] = [
                f"[开始] 扫描时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ]
            if not self.get_state():
                logs.append("[跳过] 插件未启用。")
                self._last_log = logs
                self._message = "插件未启用，已跳过。"
                logger.info(self._message)
                return

            helper = DownloaderHelper()
            services = helper.get_services() or []
            qb_services = [s for s in services if getattr(s, "type", "") == "qbittorrent"]

            if not qb_services:
                msg = "未找到已启用的 qBittorrent 下载器，跳过本次扫描。"
                logs.append(f"[警告] {msg}")
                self._last_log = logs
                self._message = msg
                logger.info(msg)
                return

            target_tags = {t.strip().lower() for t in self._only_tag.split(",") if t.strip()}
            target_trackers = [t.strip().lower() for t in self._only_tracker.split(",") if t.strip()]
            total_fixed = 0
            total_skipped = 0

            logs.append(f"[信息] 发现 {len(qb_services)} 个 qBittorrent 下载器，"
                         f"标签过滤={self._only_tag or '无'}，站点过滤={self._only_tracker or '无'}")

            for service in qb_services:
                downloader = service.instance
                name = getattr(service, "name", "unknown")
                try:
                    # get_torrents() 返回 (list, error) 元组
                    torrents, error = downloader.get_torrents()
                except Exception as e:  # noqa: BLE001
                    logs.append(f"[错误] 读取下载器 {name} 种子列表失败：{str(e)}")
                    logger.error(f"读取下载器 {name} 种子列表失败：{str(e)}")
                    continue

                if error:
                    logs.append(f"[错误] 下载器 {name} 返回错误：{error}")
                    logger.error(f"下载器 {name} 返回错误：{error}")
                    continue
                if not torrents:
                    logs.append(f"[信息] 下载器 {name} 无种子。")
                    continue

                logs.append(f"[信息] 下载器 {name} 共 {len(torrents)} 个种子。")

                for torrent in torrents:
                    t_hash = torrent.get("hash")
                    t_name = torrent.get("name", t_hash)
                    if not t_hash:
                        continue

                    # 标签过滤
                    if target_tags:
                        tags = {str(t).lower() for t in (torrent.get("tags") or [])}
                        if not (target_tags & tags):
                            continue

                    # 站点过滤：取种子所有 tracker 的域名进行匹配
                    if target_trackers:
                        trackers = torrent.get("trackers") or []
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
                        files = downloader.get_files(t_hash) or []
                    except Exception as e:  # noqa: BLE001
                        logs.append(f"[错误] 读取种子 {t_name} 文件列表失败：{str(e)}")
                        logger.error(f"读取种子 {t_name} 文件列表失败：{str(e)}")
                        continue

                    if not files:
                        continue

                    # qBittorrent 文件列表字段为 index / priority
                    mixed_ids = [
                        int(f.get("index"))
                        for f in files
                        if int(f.get("priority", 1) or 1) == 0
                    ]

                    if not mixed_ids:
                        # 全部文件都在下载，属于正常状态
                        continue

                    total_skipped += 1
                    line = f"[{name}] {t_name}（{len(mixed_ids)}/{len(files)} 个文件被取消）"
                    logs.append(f"[发现] {line}")
                    logger.info(f"发现混合状态种子：{line}")

                    if self._notify_only:
                        logs.append(f"[仅通知] {t_name} 未修改（仅通知不处理）。")
                        continue

                    try:
                        # 将全部文件优先级恢复为 1（正常），即把混合状态改为正常
                        all_ids = [int(f.get("index")) for f in files]
                        downloader.set_files(torrent_hash=t_hash, file_ids=all_ids, priority=1)
                        total_fixed += 1
                        logs.append(f"[已修复] {t_name}")
                        logger.info(f"已修复种子：{t_name}")
                    except Exception as e:  # noqa: BLE001
                        logs.append(f"[错误] 修复种子 {t_name} 失败：{str(e)}")
                        logger.error(f"修复种子 {t_name} 失败：{str(e)}")

            summary = (f"[完成] 扫描 {len(qb_services)} 个下载器，"
                       f"发现 {total_skipped} 个混合种子，"
                       f"{'仅通知不处理' if self._notify_only else f'已修复 {total_fixed} 个'}。")
            logs.append(summary)
            self._last_log = logs
            self._message = summary
            logger.info(summary)

            if self._notify:
                self.post_message(
                    title="qBittorrent 混合种子修复",
                    message="\n".join(logs),
                )
