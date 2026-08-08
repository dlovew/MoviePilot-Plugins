from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

import pytz
import re
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.helper.downloader import DownloaderHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import ServiceInfo
from app.schemas.types import EventType


class QbTorrentFixer(_PluginBase):
    # 插件在界面中的展示名称
    plugin_name = "qBittorrent 混合种子修复 -dlovew"
    # 插件描述
    plugin_desc = (
        "定时扫描 qBittorrent 中因 MoviePilot 拆包只下载合集最后一集"
        "而处于混合状态的种子，将其全部文件优先级恢复为正常。"
    )
    # 插件图标
    plugin_icon = "qBittorrent_A.png"
    # 插件版本，必须和 package.v2.json 中保持一致
    plugin_version = "1.0.6"
    # 作者信息
    plugin_author = "dlovew"
    author_url = "https://github.com/dlovew"
    # 配置项前缀，保持唯一
    plugin_config_prefix = "qbtorrentfixerdlovew_"
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
    _downloaders: List[str] = []
    _only_tag = ""
    _only_tracker = ""
    _notify_only = False
    _notify = True
    _onlyonce = False
    # 运行日志
    _message = "插件尚未初始化"
    _last_log: List[str] = []
    # 已处理的种子（展示在「数据」页）
    # 元素: {"name":..., "downloader":..., "mixed":被取消文件数, "total":文件总数, "fixed":是否已修复}
    _processed: List[Dict[str, Any]] = []

    def init_plugin(self, config: dict = None):
        self.stop_service()
        self._lock = RLock()
        config = config or {}
        self._enabled = config.get("enabled") or False
        self._cron = config.get("cron") or "0 * * * *"
        self._downloaders = config.get("downloaders") or []
        self._only_tag = config.get("only_tag") or ""
        self._only_tracker = config.get("only_tracker") or ""
        self._notify_only = config.get("notify_only") or False
        self._notify = config.get("notify", True)
        self._onlyonce = config.get("onlyonce") or False
        self._message = "插件已初始化，尚未运行过扫描。"
        self._last_log = []
        self._processed = []

        # 「立即运行一次」：独立于「启用插件」，开关打开并保存后延迟 3 秒触发一次扫描，随后复位开关
        if self._onlyonce:
            logger.info("检测到「立即运行一次」，将延迟触发一次扫描")
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.scan_and_fix,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                kwargs={"manual": True},
            )
            self._onlyonce = False
            self.update_config({
                "enabled": self._enabled,
                "cron": self._cron,
                "downloaders": self._downloaders,
                "only_tag": self._only_tag,
                "only_tracker": self._only_tracker,
                "notify_only": self._notify_only,
                "notify": self._notify,
                "onlyonce": False,
            })
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @property
    def service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        获取可用的 qBittorrent 下载器服务
        未在配置中选择下载器时，默认使用全部已启用的 qBittorrent
        """
        helper = DownloaderHelper()
        # get_services 返回的是 {名称: ServiceInfo} 字典
        services = helper.get_services(
            type_filter="qbittorrent",
            name_filters=self._downloaders or None,
        )
        if not services:
            logger.warning("获取 qBittorrent 下载器实例失败，请检查下载器配置")
            return None

        active_services = {}
        for service_name, service_info in services.items():
            if not service_info.instance:
                logger.warning(f"下载器 {service_name} 实例不可用，已跳过")
            elif service_info.instance.is_inactive():
                logger.warning(f"下载器 {service_name} 未连接，请检查配置")
            else:
                active_services[service_name] = service_info

        if not active_services:
            logger.warning("没有已连接的 qBittorrent 下载器，请检查配置")
            return None

        return active_services

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
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "multiple": True,
                                            "chips": True,
                                            "clearable": True,
                                            "model": "downloaders",
                                            "label": "下载器（留空=全部已启用的 qBittorrent）",
                                            "items": [
                                                {"title": config.name, "value": config.name}
                                                for config in DownloaderHelper().get_configs().values()
                                                if config.type == "qbittorrent"
                                            ],
                                        },
                                    }
                                ],
                            }
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
                                            "label": "立即运行一次（无需启用插件，保存后触发，运行完自动关闭）",
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
                                            "text": "本插件会扫描选定的 qBittorrent 下载器（留空则为全部已启用的 qB），"
                                                    "将处于「混合」状态（部分文件未选中）的种子全部文件"
                                                    "优先级恢复为正常，从而把状态由混合改回正常。"
                                                    "「立即运行一次」独立于「启用插件」，未启用插件时也可手动执行；"
                                                    "「启用插件」仅控制定时任务是否注册。",
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
            "downloaders": [],
            "only_tag": "",
            "only_tracker": "",
            "notify_only": False,
            "notify": True,
            "onlyonce": False,
        }

    def get_page(self) -> List[dict]:
        # 「数据」标签页：以表格展示已处理的混合种子
        if not self._processed:
            return [
                {
                    "component": "div",
                    "text": "尚未处理过任何混合种子。点击下方「立即运行一次」开始扫描。",
                    "props": {"class": "text-center"},
                }
            ]
        processed = sorted(self._processed, key=lambda x: x.get("time") or "", reverse=True)
        rows = []
        for item in processed:
            status = "已修复" if item.get("fixed") else "仅通知"
            rows.append({
                "component": "tr",
                "content": [
                    {"component": "td", "text": item.get("time")},
                    {"component": "td", "text": item.get("name")},
                    {"component": "td", "text": item.get("downloader")},
                    {"component": "td", "text": status},
                    {"component": "td", "text": f"{item.get('mixed')}/{item.get('total')}"},
                ],
            })
        return [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "content": [
                            {
                                "component": "VTable",
                                "props": {"hover": True},
                                "content": [
                                    {
                                        "component": "thead",
                                        "content": [
                                            {
                                                "component": "tr",
                                                "content": [
                                                    {"component": "th", "text": "处理时间"},
                                                    {"component": "th", "text": "种子名称"},
                                                    {"component": "th", "text": "下载器"},
                                                    {"component": "th", "text": "状态"},
                                                    {"component": "th", "text": "被取消文件"},
                                                ],
                                            }
                                        ],
                                    },
                                    {"component": "tbody", "content": rows},
                                ],
                            }
                        ],
                    }
                ],
            }
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
        # 远程命令为手动触发，同样不受「启用插件」限制
        self.scan_and_fix(manual=True)

    # ------------------------------------------------------------------ #
    # 核心逻辑
    # ------------------------------------------------------------------ #
    @staticmethod
    def __get_file_field(file_item, key: str, default=None):
        """
        兼容读取种子文件字段
        qbittorrent-api 返回的是 TorrentFile 对象，既支持 get() 也支持属性访问
        """
        try:
            value = file_item.get(key)
        except Exception:  # noqa: BLE001
            value = getattr(file_item, key, None)
        return default if value is None else value

    @classmethod
    def __get_file_id(cls, file_item) -> Optional[int]:
        """
        获取文件 ID，主程序统一使用 id 字段，缺失时回退 index
        """
        value = cls.__get_file_field(file_item, "id")
        if value is None:
            value = cls.__get_file_field(file_item, "index")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def __get_file_priority(cls, file_item) -> int:
        """
        获取文件优先级，0 表示不下载
        """
        try:
            return int(cls.__get_file_field(file_item, "priority", 1))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def __get_torrent_domains(torrent) -> set:
        """
        获取种子的 tracker 域名集合
        torrents_info 只返回当前生效的 tracker，做种完成时可能为空，
        此时回退到 qb 接口查询该种子的完整 tracker 列表
        """
        domains = set()

        def _add(url: str):
            if not url:
                return
            m = re.search(r"^(?:https?|udp)://([^:/]+)", str(url), re.IGNORECASE)
            if m:
                domains.add(m.group(1).lower())

        _add(torrent.get("tracker"))
        if not domains:
            try:
                # 回退：读取种子的全部 tracker
                trackers = torrent.trackers or []
                for tr in trackers:
                    _add(tr.get("url") if isinstance(tr, dict) else tr)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"获取种子 tracker 列表失败：{str(e)}")
        return domains

    def scan_and_fix(self, manual: bool = False):
        """
        扫描 qBittorrent 下载器，修复混合状态种子
        :param manual: 是否为手动触发（「立即运行一次」/远程命令），手动触发不受「启用插件」限制
        """
        with self._lock:
            logs: List[str] = [
                f"[开始] 扫描时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                f"{'（手动触发）' if manual else ''}"
            ]
            if not manual and not self.get_state():
                logs.append("[跳过] 插件未启用。")
                self._last_log = logs
                self._message = "插件未启用，已跳过。"
                logger.info(self._message)
                return

            service_infos = self.service_infos
            if not service_infos:
                msg = "未找到已连接的 qBittorrent 下载器，跳过本次扫描。"
                logs.append(f"[警告] {msg}")
                self._last_log = logs
                self._message = msg
                logger.warning(msg)
                return

            target_tags = {t.strip().lower() for t in self._only_tag.split(",") if t.strip()}
            target_trackers = [t.strip().lower() for t in self._only_tracker.split(",") if t.strip()]
            total_fixed = 0
            total_skipped = 0
            total_checked = 0
            # 本次扫描发现的混合种子（用于「数据」页展示与通知推送）
            mixed_torrents: List[Dict[str, Any]] = []

            logs.append(f"[信息] 发现 {len(service_infos)} 个可用 qBittorrent 下载器，"
                        f"标签过滤={self._only_tag or '无'}，站点过滤={self._only_tracker or '无'}")

            for name, service in service_infos.items():
                downloader = service.instance
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
                    logger.info(f"下载器 {name} 无种子")
                    continue

                logs.append(f"[信息] 下载器 {name} 共 {len(torrents)} 个种子。")
                logger.info(f"下载器 {name} 共 {len(torrents)} 个种子，开始检查")

                for torrent in torrents:
                    t_hash = torrent.get("hash")
                    t_name = torrent.get("name", t_hash)
                    if not t_hash:
                        continue

                    # 标签过滤：qB 的 tags 是逗号分隔的字符串
                    if target_tags:
                        raw_tags = torrent.get("tags") or ""
                        if isinstance(raw_tags, str):
                            tags = {t.strip().lower() for t in raw_tags.split(",") if t.strip()}
                        else:
                            tags = {str(t).strip().lower() for t in raw_tags}
                        if not (target_tags & tags):
                            continue

                    # 站点过滤：匹配种子当前 tracker 的域名
                    if target_trackers:
                        domains = self.__get_torrent_domains(torrent)
                        if not any(tk in d for d in domains for tk in target_trackers):
                            continue

                    total_checked += 1

                    # 判定是否为「混合」状态：存在未选中的文件（priority == 0）
                    try:
                        files = downloader.get_files(t_hash) or []
                    except Exception as e:  # noqa: BLE001
                        logs.append(f"[错误] 读取种子 {t_name} 文件列表失败：{str(e)}")
                        logger.error(f"读取种子 {t_name} 文件列表失败：{str(e)}")
                        continue

                    if not files:
                        continue

                    # 单文件种子不存在「混合」概念，直接跳过
                    if len(files) <= 1:
                        continue

                    # 注意：priority 为 0 表示不下载，不能写成 `or 1`，
                    # 否则 0 会被判定为假值而被替换成 1，导致永远发现不了混合种子
                    all_ids = [self.__get_file_id(f) for f in files]
                    mixed_ids = [
                        self.__get_file_id(f)
                        for f in files
                        if self.__get_file_priority(f) == 0
                    ]

                    if None in all_ids:
                        logs.append(f"[跳过] {t_name} 文件列表缺少 id 字段，无法处理。")
                        logger.warning(f"种子 {t_name} 文件列表缺少 id 字段，无法处理")
                        continue

                    if not mixed_ids:
                        # 全部文件都在下载，属于正常状态
                        continue

                    total_skipped += 1
                    line = f"[{name}] {t_name}（{len(mixed_ids)}/{len(files)} 个文件被取消）"
                    logs.append(f"[发现] {line}")
                    logger.info(f"发现混合状态种子：{line}")

                    record = {
                        "name": t_name,
                        "downloader": name,
                        "mixed": len(mixed_ids),
                        "total": len(files),
                        "fixed": False,
                        "time": datetime.now(tz=pytz.timezone(settings.TZ)).strftime("%Y-%m-%d %H:%M:%S"),
                    }

                    if self._notify_only:
                        logs.append(f"[仅通知] {t_name} 未修改（仅通知不处理）。")
                        mixed_torrents.append(record)
                        continue

                    try:
                        # 将全部文件优先级恢复为 1（正常），即把混合状态改为正常
                        # set_files 返回 bool，不抛异常
                        if downloader.set_files(torrent_hash=t_hash, file_ids=all_ids, priority=1):
                            total_fixed += 1
                            record["fixed"] = True
                            logs.append(f"[已修复] {t_name}")
                            logger.info(f"已修复种子：{t_name}")
                        else:
                            logs.append(f"[错误] 修复种子 {t_name} 失败，下载器返回失败")
                            logger.error(f"修复种子 {t_name} 失败，下载器返回失败")
                    except Exception as e:  # noqa: BLE001
                        logs.append(f"[错误] 修复种子 {t_name} 失败：{str(e)}")
                        logger.error(f"修复种子 {t_name} 失败：{str(e)}")
                    mixed_torrents.append(record)

            summary = (f"[完成] 扫描 {len(service_infos)} 个下载器，"
                       f"过滤后检查 {total_checked} 个种子，"
                       f"发现 {total_skipped} 个混合种子，"
                       f"{'仅通知不处理' if self._notify_only else f'已修复 {total_fixed} 个'}。")
            logs.append(summary)
            self._last_log = logs
            self._message = summary
            self._processed = mixed_torrents
            logger.info(summary)

            if self._notify and mixed_torrents:
                fixed_count = sum(1 for t in mixed_torrents if t.get("fixed"))
                notify_lines = [
                    f"共处理 {len(mixed_torrents)} 个混合种子"
                    + (f"（已修复 {fixed_count} 个）" if not self._notify_only else "（仅通知）") + "："
                ]
                for t in mixed_torrents:
                    status = "已修复" if t.get("fixed") else "未处理"
                    notify_lines.append(f"· {t.get('name')}（{status} | "
                                        f"{t.get('mixed')}/{t.get('total')} 文件被取消）")
                self.post_message(
                    title="qBittorrent 混合种子修复",
                    text="\n".join(notify_lines),
                )
