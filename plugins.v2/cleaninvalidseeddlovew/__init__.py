import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.utils.string import StringUtils
from app.schemas.types import EventType
from app.schemas import ServiceInfo
from app.core.event import eventmanager, Event

from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional
from app.log import logger
from app.schemas import NotificationType
from app.helper.downloader import DownloaderHelper

class CleanInvalidSeeddlovew(_PluginBase):
    # 插件名称
    plugin_name = "清理无效做种 -dlovew"
    # 插件描述
    plugin_desc = "清理已经被站点删除的种子及源文件，支持qBittorrent和Transmission"
    # 插件图标
    plugin_icon = "clean_a.png"
    # 插件版本
    plugin_version = "2.2"
    # 插件作者
    plugin_author = "dlovew"
    # 作者主页
    author_url = "https://github.com/dlovew"
    # 插件配置项ID前缀
    plugin_config_prefix = "cleaninvalidseeddlovew_"
    # 加载顺序
    plugin_order = 1
    # 可使用的用户级别
    auth_level = 1

    # 日志标签
    LOG_TAG = "[CleanInvalidSeed]"

    # 私有属性
    _enabled = False
    _cron = None
    _notify = False
    _onlyonce = False
    _detect_invalid_files = False
    _delete_invalid_files = False
    _delete_invalid_torrents = False
    _notify_all = False
    _label_only = False
    _label = ""
    _download_dirs = ""
    _exclude_keywords = ""
    _exclude_categories = ""
    _exclude_labels = ""
    _more_logs = False
    _min_seeding_days = 0  # 最小做种天数，0表示不限制
    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None
    _error_msg = [
        "torrent not registered with this tracker",
        "Torrent not registered with this tracker",
        "torrent banned",
        "err torrent banned",
        "Torrent not exists",
    ]
    _custom_error_msg = ""

    def init_plugin(self, config: dict = None):
        self.downloader_helper = DownloaderHelper()
        # 停止现有任务
        self.stop_service()

        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._notify = config.get("notify")
            self._onlyonce = config.get("onlyonce")
            self._delete_invalid_torrents = config.get("delete_invalid_torrents")
            self._delete_invalid_files = config.get("delete_invalid_files")
            self._detect_invalid_files = config.get("detect_invalid_files")
            self._notify_all = config.get("notify_all")
            self._label_only = config.get("label_only")
            self._label = config.get("label")
            self._download_dirs = config.get("download_dirs")
            self._exclude_keywords = config.get("exclude_keywords")
            self._exclude_categories = config.get("exclude_categories")
            self._exclude_labels = config.get("exclude_labels")
            self._custom_error_msg = config.get("custom_error_msg")
            self._more_logs = config.get("more_logs")
            self._downloaders = config.get("downloaders")
            # 确保最小做种天数是整数类型
            min_seeding_days_raw = config.get("min_seeding_days", 0)
            try:
                self._min_seeding_days = int(min_seeding_days_raw) if min_seeding_days_raw is not None else 0
            except (ValueError, TypeError):
                logger.warning(f"无效的最小做种天数配置: {min_seeding_days_raw}，使用默认值 0")
                self._min_seeding_days = 0

            # 加载模块
        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            logger.info(f"清理无效种子服务启动，立即运行一次")
            self._scheduler.add_job(
                func=self.clean_invalid_seed,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ))
                + timedelta(seconds=3),
                name="清理无效种子",
            )
            # 关闭一次性开关
            self._onlyonce = False
            self._update_config()

            # 启动任务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    def _update_config(self):
        self.update_config(
            {
                "onlyonce": False,
                "cron": self._cron,
                "enabled": self._enabled,
                "notify": self._notify,
                "delete_invalid_torrents": self._delete_invalid_torrents,
                "delete_invalid_files": self._delete_invalid_files,
                "detect_invalid_files": self._detect_invalid_files,
                "notify_all": self._notify_all,
                "label_only": self._label_only,
                "label": self._label,
                "download_dirs": self._download_dirs,
                "exclude_keywords": self._exclude_keywords,
                "exclude_categories": self._exclude_categories,
                "exclude_labels": self._exclude_labels,
                "custom_error_msg": self._custom_error_msg,
                "more_logs": self._more_logs,
                "downloaders": self._downloaders,
                "min_seeding_days": self._min_seeding_days,
            }
        )

    @property
    def service_info(self) -> Optional[ServiceInfo]:
        """
        服务信息
        """
        if not self._downloaders:
            logger.warning("尚未配置下载器，请检查配置")
            return None

        services = self.downloader_helper.get_services(name_filters=self._downloaders)

        if not services:
            logger.warning("获取下载器实例失败，请检查配置")
            return None

        active_services = {}
        for service_name, service_info in services.items():
            if service_info.instance.is_inactive():
                logger.warning(f"下载器 {service_name} 未连接，请检查配置")
            elif not self.check_is_supported_downloader(service_info):
                downloader_type = self.get_downloader_type(service_info)
                logger.warning(f"不支持的下载器类型 {service_name} ({downloader_type})，仅支持qBittorrent和Transmission，请检查配置")
            else:
                active_services[service_name] = service_info

        if not active_services:
            logger.warning("没有已连接的下载器，请检查配置")
            return None

        return active_services

    def check_is_supported_downloader(self, service_info) -> bool:
        """
        检查下载器类型是否为支持的类型（qbittorrent 或 transmission）
        """
        return (self.downloader_helper.is_downloader(service_type="qbittorrent", service=service_info) or
                self.downloader_helper.is_downloader(service_type="transmission", service=service_info))

    def get_downloader_type(self, service_info) -> str:
        """
        获取下载器类型
        """
        if self.downloader_helper.is_downloader(service_type="qbittorrent", service=service_info):
            return "qbittorrent"
        elif self.downloader_helper.is_downloader(service_type="transmission", service=service_info):
            return "transmission"
        return "unknown"

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [
            {
                "cmd": "/detect_invalid_torrents",
                "event": EventType.PluginAction,
                "desc": "检测无效做种",
                "category": "下载器",
                "data": {"action": "detect_invalid_torrents"},
            },
            {
                "cmd": "/delete_invalid_torrents",
                "event": EventType.PluginAction,
                "desc": "清理无效做种",
                "category": "下载器",
                "data": {"action": "delete_invalid_torrents"},
            },
            {
                "cmd": "/detect_invalid_files",
                "event": EventType.PluginAction,
                "desc": "检测无效源文件",
                "category": "下载器",
                "data": {"action": "detect_invalid_files"},
            },
            {
                "cmd": "/delete_invalid_files",
                "event": EventType.PluginAction,
                "desc": "清理无效源文件",
                "category": "下载器",
                "data": {"action": "delete_invalid_files"},
            },
            {
                "cmd": "/toggle_notify_all",
                "event": EventType.PluginAction,
                "desc": "清理插件切换全量通知",
                "category": "下载器",
                "data": {"action": "toggle_notify_all"},
            },
        ]

    @eventmanager.register(EventType.PluginAction)
    def handle_commands(self, event: Event):
        if event:
            event_data = event.event_data
            if event_data:
                if not (
                    event_data.get("action") == "detect_invalid_torrents"
                    or event_data.get("action") == "delete_invalid_torrents"
                    or event_data.get("action") == "detect_invalid_files"
                    or event_data.get("action") == "delete_invalid_files"
                    or event_data.get("action") == "toggle_notify_all"
                ):
                    return
                self.post_message(
                    channel=event.event_data.get("channel"),
                    title="🚀 开始执行远程命令...",
                    userid=event.event_data.get("user"),
                )
                old_delete_invalid_torrents = self._delete_invalid_torrents
                old_detect_invalid_files = self._detect_invalid_files
                old_delete_invalid_files = self._delete_invalid_files
                if event_data.get("action") == "detect_invalid_torrents":
                    logger.info("收到远程命令，开始检测无效做种")
                    self._delete_invalid_torrents = False
                    self._detect_invalid_files = False
                    self._delete_invalid_files = False
                    self.clean_invalid_seed()
                elif event_data.get("action") == "delete_invalid_torrents":
                    logger.info("收到远程命令，开始清理无效做种")
                    self._delete_invalid_torrents = True
                    self._detect_invalid_files = False
                    self._delete_invalid_files = False
                    self.clean_invalid_seed()
                elif event_data.get("action") == "detect_invalid_files":
                    logger.info("收到远程命令，开始检测无效源文件")
                    self._delete_invalid_files = False
                    self.detect_invalid_files()
                elif event_data.get("action") == "delete_invalid_files":
                    logger.info("收到远程命令，开始清理无效源文件")
                    self._delete_invalid_files = True
                    self.detect_invalid_files()
                elif event_data.get("action") == "toggle_notify_all":
                    self._notify_all = not self._notify_all
                    self._update_config()
                    if self._notify_all:
                        self.post_message(
                            channel=event.event_data.get("channel"),
                            title="🔔 已开启全量通知",
                            userid=event.event_data.get("user"),
                        )
                    else:
                        self.post_message(
                            channel=event.event_data.get("channel"),
                            title="🔕 已关闭全量通知",
                            userid=event.event_data.get("user"),
                        )
                    return
                else:
                    logger.error("收到未知远程命令")
                    return
                self._delete_invalid_torrents = old_delete_invalid_torrents
                self._detect_invalid_files = old_detect_invalid_files
                self._delete_invalid_files = old_delete_invalid_files
                self.post_message(
                    channel=event.event_data.get("channel"),
                    title="✅ 远程命令执行完成！",
                    userid=event.event_data.get("user"),
                )

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        if self._enabled and self._cron:
            return [
                {
                    "id": "CleanInvalidSeed",
                    "name": "清理无效做种",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.clean_invalid_seed,
                    "kwargs": {},
                }
            ]

    def get_all_torrents(self, service):
        downloader_name = service.name
        downloader_obj = service.instance

        try:
            logger.debug(f"开始获取下载器 {downloader_name} 的种子列表...")
            all_torrents, error = downloader_obj.get_torrents()
            logger.debug(f"下载器 {downloader_name} get_torrents 返回: torrents数量={len(all_torrents) if all_torrents else 0}, error={error}")
        except Exception as e:
            logger.error(f"调用下载器 {downloader_name} get_torrents 方法时出错: {e}")
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=f"❌ 【清理无效做种】",
                    text=f"获取下载器 {downloader_name} 种子失败，请检查下载器配置",
                )
            return []

        if error:
            logger.error(f"获取下载器:{downloader_name}种子失败: {error}")
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=f"❌ 【清理无效做种】",
                    text=f"获取下载器 {downloader_name} 种子失败，请检查下载器配置",
                )
            return []

        if not all_torrents:
            logger.warning(f"下载器:{downloader_name} 中没有种子")
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=f"ℹ️ 【清理无效做种】",
                    text=f"下载器 {downloader_name} 中没有种子",
                )
            return []

        logger.debug(f"成功获取下载器 {downloader_name} 的 {len(all_torrents)} 个种子")
        return all_torrents

    def get_tracker_info(self, torrent, downloader_type):
        """
        获取种子的tracker信息，兼容qBittorrent和Transmission
        """
        trackers = []

        try:
            if downloader_type == "qbittorrent":
                # qBittorrent使用trackers属性
                if hasattr(torrent, 'trackers') and torrent.trackers:
                    trackers = torrent.trackers
            elif downloader_type == "transmission":
                # 首先检查Transmission的error和errorString属性
                error_code = self.safe_getattr(torrent, 'error', 0, timeout=3)
                error_string = self.safe_getattr(torrent, 'errorString', '', timeout=3)
                # 也检查error_string属性（下划线命名）
                if not error_string:
                    error_string = self.safe_getattr(torrent, 'error_string', '', timeout=3)

                if self._more_logs:
                    logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] error_code: {error_code}, error_string: '{error_string}'")

                # 仅在更多日志模式下检查种子属性
                if self._more_logs:
                    torrent_attrs = []
                    for attr in ['trackerStats', 'trackers', 'trackerList']:
                        if self.safe_hasattr(torrent, attr, timeout=1):
                            attr_value = self.safe_getattr(torrent, attr, None, timeout=2)
                            if attr_value is not None:
                                if hasattr(attr_value, '__len__'):
                                    torrent_attrs.append(f"{attr}={type(attr_value).__name__}({len(attr_value)})")
                                else:
                                    torrent_attrs.append(f"{attr}={type(attr_value).__name__}({attr_value})")
                            else:
                                torrent_attrs.append(f"{attr}=None")
                        else:
                            torrent_attrs.append(f"{attr}=NotFound")
                    logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] 属性检查: {', '.join(torrent_attrs)}")



                # 如果有错误，创建一个合成的tracker条目来表示错误状态
                if (error_code and error_code != 0) or (error_string and error_string.strip()):
                    # 尝试从trackerStats获取第一个tracker的URL，如果没有则使用默认值
                    tracker_url = "unknown"
                    if self.safe_hasattr(torrent, 'trackerStats', timeout=2):
                        tracker_stats = self.safe_getattr(torrent, 'trackerStats', [], timeout=3)
                        if tracker_stats and len(tracker_stats) > 0:
                            tracker_url = tracker_stats[0].get("announce", "unknown")
                    elif self.safe_hasattr(torrent, 'trackers', timeout=2):
                        # 有些Transmission版本可能也有trackers属性
                        trackers_list = self.safe_getattr(torrent, 'trackers', [], timeout=3)
                        tracker_url = trackers_list[0] if trackers_list else "unknown"
                    elif self.safe_hasattr(torrent, 'trackerList', timeout=2):
                        # 尝试trackerList属性
                        tracker_list = self.safe_getattr(torrent, 'trackerList', [], timeout=3)
                        if tracker_list and len(tracker_list) > 0:
                            # trackerList可能是字符串列表
                            tracker_url = tracker_list[0] if isinstance(tracker_list[0], str) else tracker_list[0].get("announce", "unknown")

                    # 创建错误tracker条目
                    error_tracker = {
                        "url": tracker_url,
                        "status": 4,  # 错误状态
                        "msg": error_string.strip() if error_string else f"Error code: {error_code}",
                        "tier": 0
                    }
                    trackers.append(error_tracker)
                    if self._more_logs:
                        logger.debug(f"为种子 [{getattr(torrent, 'name', 'Unknown')}] 创建错误tracker: {error_tracker}")

                # 处理正常的trackerStats（尝试两种命名方式）
                tracker_stats = None
                if self.safe_hasattr(torrent, 'trackerStats', timeout=2):
                    tracker_stats = self.safe_getattr(torrent, 'trackerStats', [], timeout=3)
                elif self.safe_hasattr(torrent, 'tracker_stats', timeout=2):
                    tracker_stats = self.safe_getattr(torrent, 'tracker_stats', [], timeout=3)

                if tracker_stats:
                    if self._more_logs:
                        logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] tracker_stats: {len(tracker_stats)} 个")
                    # 转换Transmission的trackerStats格式为统一格式
                    for i, tracker_stat in enumerate(tracker_stats):
                        try:
                            # 检查tracker_stat的类型和内容
                            # logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] tracker_stat[{i}] type: {type(tracker_stat)}, content: {tracker_stat}")

                            # 如果是字典类型
                            if isinstance(tracker_stat, dict):
                                tracker_info = {
                                    "url": tracker_stat.get("announce", ""),
                                    "status": self.convert_transmission_tracker_status(tracker_stat),
                                    "msg": tracker_stat.get("lastAnnounceResult", ""),
                                    "tier": tracker_stat.get("tier", 0)
                                }
                            # 如果是对象类型（TrackerStats对象）
                            else:
                                announce = getattr(tracker_stat, 'announce', '') or getattr(tracker_stat, 'announceUrl', '')
                                last_announce_result = getattr(tracker_stat, 'last_announce_result', '') or getattr(tracker_stat, 'lastAnnounceResult', '')
                                last_announce_succeeded = getattr(tracker_stat, 'last_announce_succeeded', True)
                                if last_announce_succeeded is None:
                                    last_announce_succeeded = getattr(tracker_stat, 'lastAnnounceSucceeded', True)
                                tier = getattr(tracker_stat, 'tier', i)

                                # 根据announce结果判断状态
                                # 检查错误消息是否匹配我们的错误列表
                                is_error_msg = False
                                if last_announce_result:
                                    # 获取当前的错误消息列表
                                    custom_msgs = (
                                        self._custom_error_msg.split("\n") if self._custom_error_msg else []
                                    )
                                    # 过滤掉空字符串
                                    custom_msgs = [msg.strip() for msg in custom_msgs if msg.strip()]
                                    error_msgs = self._error_msg + custom_msgs
                                    is_error_msg = last_announce_result in error_msgs

                                    # 仅在更多日志模式下添加调试信息
                                    if self._more_logs:
                                        logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] tracker错误检查: last_announce_result='{last_announce_result}', is_error_msg={is_error_msg}")

                                if not last_announce_succeeded or is_error_msg:
                                    status = 4  # 错误状态
                                elif last_announce_succeeded and last_announce_result == "Success":
                                    status = 2  # 正常工作
                                else:
                                    status = 1  # 其他状态

                                tracker_info = {
                                    "url": announce,
                                    "status": status,
                                    "msg": last_announce_result,
                                    "tier": tier
                                }

                            trackers.append(tracker_info)
                            # logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] tracker[{i}]: url={tracker_info['url'][:50]}..., status={tracker_info['status']}, msg='{tracker_info['msg']}'")
                        except Exception as e:
                            logger.error(f"处理种子 [{getattr(torrent, 'name', 'Unknown')}] tracker[{i}] 时出错: {e}")
                else:
                    logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] 没有找到 trackerStats 或 tracker_stats 属性")

                # 尝试其他可能的tracker属性
                if not trackers:
                    logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] 没有从trackerStats获取到tracker，尝试其他属性...")

                    # 尝试trackers属性 (Transmission的Tracker对象列表)
                    if self.safe_hasattr(torrent, 'trackers', timeout=2):
                        trackers_list = self.safe_getattr(torrent, 'trackers', [], timeout=3)
                        logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] trackers: {trackers_list}")
                        if trackers_list:
                            for i, tracker_obj in enumerate(trackers_list):
                                try:
                                    # Transmission的Tracker对象有announce属性
                                    tracker_url = getattr(tracker_obj, 'announce', str(tracker_obj))

                                    # 检查Tracker对象的错误状态
                                    # Transmission Tracker对象可能有lastAnnounceResult等属性
                                    last_announce_result = getattr(tracker_obj, 'lastAnnounceResult', '')
                                    last_announce_succeeded = getattr(tracker_obj, 'lastAnnounceSucceeded', True)

                                    # 根据announce结果判断状态
                                    if last_announce_result and not last_announce_succeeded:
                                        status = 4  # 错误状态
                                    elif last_announce_succeeded:
                                        status = 2  # 正常工作
                                    else:
                                        status = 1  # 其他状态

                                    tracker_info = {
                                        "url": tracker_url,
                                        "status": status,
                                        "msg": last_announce_result,
                                        "tier": i
                                    }
                                    trackers.append(tracker_info)
                                    # logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] tracker[{i}]: url={tracker_url[:50]}..., status={status}, msg='{last_announce_result}'")
                                except Exception as e:
                                    logger.error(f"处理种子 [{getattr(torrent, 'name', 'Unknown')}] tracker对象[{i}] 时出错: {e}")
                                    # 如果无法处理Tracker对象，至少创建一个基本的tracker条目
                                    tracker_info = {
                                        "url": str(tracker_obj),
                                        "status": 2,  # 假设正常工作
                                        "msg": "",
                                        "tier": i
                                    }
                                    trackers.append(tracker_info)

                    # 尝试trackerList属性
                    elif self.safe_hasattr(torrent, 'trackerList', timeout=2):
                        tracker_list = self.safe_getattr(torrent, 'trackerList', [], timeout=3)
                        logger.debug(f"种子 [{getattr(torrent, 'name', 'Unknown')}] trackerList: {tracker_list}")
                        if tracker_list:
                            for i, tracker_url in enumerate(tracker_list):
                                tracker_info = {
                                    "url": tracker_url if isinstance(tracker_url, str) else str(tracker_url),
                                    "status": 2,  # 假设正常工作
                                    "msg": "",
                                    "tier": i
                                }
                                trackers.append(tracker_info)
        except Exception as e:
            logger.error(f"获取种子 [{getattr(torrent, 'name', 'Unknown')}] tracker信息时出错: {e}")
            return []

        return trackers

    def convert_transmission_tracker_status(self, tracker_stat):
        """
        将Transmission的tracker状态转换为qBittorrent兼容的状态码
        """
        # Transmission tracker状态映射
        # 0: Tracker is waiting
        # 1: Tracker is queued
        # 2: Tracker is announcing
        # 3: Tracker is working (announced successfully)
        # 4: Tracker has an error

        last_announce_succeeded = tracker_stat.get("lastAnnounceSucceeded", False)
        has_announced = tracker_stat.get("hasAnnounced", False)

        if last_announce_succeeded and has_announced:
            return 2  # 工作正常，对应qB的状态2
        elif tracker_stat.get("lastAnnounceResult"):
            return 4  # 有错误信息，对应qB的状态4
        else:
            return 1  # 其他状态，对应qB的状态1

    def is_torrent_paused(self, torrent, downloader_type):
        """
        检查种子是否暂停，兼容qBittorrent和Transmission
        """
        if downloader_type == "qbittorrent":
            return hasattr(torrent, 'state_enum') and torrent.state_enum.is_paused
        elif downloader_type == "transmission":
            # Transmission使用status属性，"stopped"表示暂停
            return hasattr(torrent, 'status') and str(torrent.status).lower() == "stopped"
        return False

    def get_torrent_category(self, torrent, downloader_type):
        """
        获取种子分类，兼容qBittorrent和Transmission
        """
        if downloader_type == "qbittorrent":
            return getattr(torrent, 'category', '')
        elif downloader_type == "transmission":
            # Transmission没有分类概念，返回空字符串
            return ''
        return ''

    def get_torrent_tags(self, torrent, downloader_type):
        """
        获取种子标签，兼容qBittorrent和Transmission
        """
        if downloader_type == "qbittorrent":
            return getattr(torrent, 'tags', '')
        elif downloader_type == "transmission":
            # Transmission使用labels属性
            labels = getattr(torrent, 'labels', [])
            if labels:
                return ','.join([str(label) for label in labels])
            return ''
        return ''

    def get_torrent_hash(self, torrent, downloader_type):
        """
        获取种子hash，兼容qBittorrent和Transmission
        """
        if downloader_type == "qbittorrent":
            # qBittorrent可以通过get方法或直接属性获取hash
            if hasattr(torrent, 'get') and callable(torrent.get):
                return torrent.get("hash")
            return getattr(torrent, 'hash', None)
        elif downloader_type == "transmission":
            # Transmission使用hashString属性
            return getattr(torrent, 'hashString', None)
        return None

    def set_torrent_label(self, downloader_obj, downloader_type, torrent_hash, torrent, label):
        """
        设置种子标签，兼容qBittorrent和Transmission
        """
        if downloader_type == "qbittorrent":
            # qBittorrent使用set_torrents_tag方法
            downloader_obj.set_torrents_tag(ids=torrent_hash, tags=[label])
        elif downloader_type == "transmission":
            # Transmission需要获取现有标签并追加新标签
            existing_labels = getattr(torrent, 'labels', [])
            existing_labels = [str(tag) for tag in existing_labels] if existing_labels else []
            if label not in existing_labels:
                existing_labels.append(label)
            downloader_obj.set_torrent_tag(ids=torrent_hash, tags=existing_labels)

    def safe_hasattr(self, obj, attr_name, timeout=3):
        """
        安全检查对象是否有属性，带超时保护
        """
        try:
            import threading
            result = [False]
            exception = [None]

            def check_attr():
                try:
                    result[0] = hasattr(obj, attr_name)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=check_attr)
            thread.daemon = True
            thread.start()
            thread.join(timeout)

            if thread.is_alive():
                logger.warning(f"检查属性 {attr_name} 超时 ({timeout}s)")
                return False

            if exception[0]:
                logger.error(f"检查属性 {attr_name} 时出错: {exception[0]}")
                return False

            return result[0]

        except Exception as e:
            logger.error(f"安全检查属性 {attr_name} 时发生异常: {e}")
            return False

    def safe_getattr(self, obj, attr_name, default=None, timeout=5):
        """
        安全获取对象属性，带超时保护
        """
        try:
            # 使用简单的超时机制
            import threading
            result = [default]
            exception = [None]

            def get_attr():
                try:
                    if hasattr(obj, attr_name):
                        result[0] = getattr(obj, attr_name)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=get_attr)
            thread.daemon = True
            thread.start()
            thread.join(timeout)

            if thread.is_alive():
                logger.warning(f"获取属性 {attr_name} 超时 ({timeout}s)")
                return default

            if exception[0]:
                logger.error(f"获取属性 {attr_name} 时出错: {exception[0]}")
                return default

            return result[0]

        except Exception as e:
            logger.error(f"安全获取属性 {attr_name} 时发生异常: {e}")
            return default



    def is_file_old_enough(self, file_path):
        """
        检查文件是否已经存在足够长时间
        """
        try:
            # 确保最小天数是数字类型
            min_days = int(self._min_seeding_days) if self._min_seeding_days is not None else 0

            if min_days <= 0:
                return True  # 不限制时间

            if not file_path.exists():
                return False

            try:
                # 获取文件的创建时间（或修改时间，取较早的）
                stat = file_path.stat()
                # 在Linux系统中，st_ctime是状态改变时间，st_mtime是修改时间
                # 我们使用修改时间作为文件的"创建"时间
                file_time = stat.st_mtime

                # 计算文件存在天数
                current_time = datetime.now().timestamp()
                file_days = (current_time - file_time) / (24 * 3600)
                result = file_days >= min_days

                return result
            except Exception as e:
                logger.error(f"计算文件存在天数时出错: {e}")
                return False

        except Exception as e:
            logger.error(f"文件时间检查过程中发生异常: {e}")
            return False

    def clean_invalid_seed(self):
        for service in self.service_info.values():
            downloader_name = service.name
            downloader_obj = service.instance
            downloader_type = self.get_downloader_type(service)

            if not downloader_obj:
                logger.error(f"{self.LOG_TAG} 获取下载器失败 {downloader_name}")
                continue
            logger.info(f"开始清理 {downloader_name} ({downloader_type}) 无效做种...")
            logger.info(f"正在获取 {downloader_name} 的种子列表...")
            all_torrents = self.get_all_torrents(service)
            logger.info(f"获取到 {len(all_torrents)} 个种子，开始分析...")
            temp_invalid_torrents = []
            # tracker未工作，但暂时不能判定为失效做种，需人工判断
            tracker_not_working_torrents = []
            working_tracker_set = set()
            exclude_categories = (
                self._exclude_categories.split("\n") if self._exclude_categories else []
            )
            exclude_labels = (
                self._exclude_labels.split("\n") if self._exclude_labels else []
            )
            custom_msgs = (
                self._custom_error_msg.split("\n") if self._custom_error_msg else []
            )
            # 过滤掉空字符串
            custom_msgs = [msg.strip() for msg in custom_msgs if msg.strip()]
            error_msgs = self._error_msg + custom_msgs

            # 仅在更多日志模式下输出调试信息
            if self._more_logs:
                logger.debug(f"默认错误消息: {self._error_msg}")
                logger.debug(f"自定义错误消息: {custom_msgs}")
                logger.debug(f"合并后错误消息列表: {error_msgs}")
            # 第一轮筛选出所有未工作的种子
            processed_count = 0
            for torrent in all_torrents:
                processed_count += 1
                if processed_count % 50 == 0:  # 每50个种子输出一次进度
                    logger.info(f"正在处理第 {processed_count}/{len(all_torrents)} 个种子...")

                try:
                    trackers = self.get_tracker_info(torrent, downloader_type)
                    if self._more_logs:
                        logger.debug(f"种子 [{torrent.name}] 获取到 {len(trackers)} 个tracker信息")

                    is_invalid = False
                    is_tracker_working = False

                    # 判定规则（按用户确认语义）：
                    #   只要存在任意一个 tracker 满足 "状态==4 且 消息子串命中错误关键词"
                    #   （兼容 (deleted) 等变体，使用子串匹配），即判定种子失效。
                    #   其余状态（未工作/timed out/状态1/无消息）一律不视为失效，也不作为健康佐证。
                    #   双 tracker 站点：只要有一个出错即失效，不要求所有 tracker 都出错。
                    for tracker in trackers:
                        if tracker.get("tier") == -1:
                            continue
                        tracker_domian = StringUtils.get_url_netloc((tracker.get("url")))[1]
                        tracker_status = tracker.get("status")
                        tracker_msg = tracker.get("msg", "") or ""

                        is_error_tracker = (tracker_status == 4) and any(
                            kw in tracker_msg for kw in error_msgs
                        )

                        if is_error_tracker:
                            is_invalid = True
                            if self._more_logs:
                                logger.debug(
                                    f"种子 [{getattr(torrent, 'name', 'Unknown')}] 命中失效 tracker: "
                                    f"{tracker_domian} - {tracker_msg}"
                                )

                        # 仅当 tracker 确认连上时才收录到 working 集合，供后续佐证使用
                        if tracker_status in (2, 3) and not any(kw in tracker_msg for kw in error_msgs):
                            is_tracker_working = True
                            working_tracker_set.add(tracker_domian)

                    if self._more_logs:
                        torrent_category = self.get_torrent_category(torrent, downloader_type)
                        torrent_tags = self.get_torrent_tags(torrent, downloader_type)
                        logger.info(f"处理 [{torrent.name}]: 分类: [{torrent_category}], 标签: [{torrent_tags}], is_invalid: [{is_invalid}], is_working: [{is_tracker_working}]")

                    if is_invalid:
                        temp_invalid_torrents.append(torrent)
                        if self._more_logs:
                            logger.debug(f"种子 [{torrent.name}] 被标记为无效")
                    elif not is_tracker_working:
                        # 排除已暂停的种子
                        if not self.is_torrent_paused(torrent, downloader_type):
                            # 收集tracker错误信息
                            tracker_error_info = []
                            for tracker in trackers:
                                if tracker.get("tier") == -1:
                                    continue
                                tracker_domain = StringUtils.get_url_netloc((tracker.get("url")))[1]
                                tracker_status = tracker.get("status")
                                tracker_msg = tracker.get("msg", "")

                                # 收集非正常工作的tracker信息
                                if tracker_status != 2 and tracker_status != 3:
                                    status_desc = {
                                        0: "未知",
                                        1: "等待中",
                                        4: "错误"
                                    }.get(tracker_status, f"状态{tracker_status}")

                                    if tracker_msg:
                                        tracker_error_info.append(f"{tracker_domain}({status_desc}: {tracker_msg})")
                                    else:
                                        tracker_error_info.append(f"{tracker_domain}({status_desc})")

                            # 保存种子和错误信息的元组
                            tracker_not_working_torrents.append((torrent, tracker_error_info))
                            if self._more_logs:
                                logger.debug(f"种子 [{torrent.name}] tracker未工作: {', '.join(tracker_error_info)}")

                except Exception as e:
                    logger.error(f"处理种子 [{getattr(torrent, 'name', 'Unknown')}] 时出错: {e}")
                    continue

            logger.info(f"初筛共有{len(temp_invalid_torrents)}个无效做种")
            # 第二轮：对初筛出的失效种子，按"排除分类/标签"过滤后执行标记/删除
            # 注：不再要求"同域名有别的种子连上"才处理，避免整站被ban时漏判。
            # 失效做种但通过种子分类排除的种子
            invalid_torrents_exclude_categories = []
            # 失效做种但通过种子标签排除的种子
            invalid_torrents_exclude_labels = []
            # 将invalid_torrents基本信息保存起来，在种子被删除后依然可以打印这些信息
            invalid_torrent_tuple_list = []
            deleted_torrent_tuple_list = []
            for torrent in temp_invalid_torrents:
                trackers = self.get_tracker_info(torrent, downloader_type)
                for tracker in trackers:
                    if tracker.get("tier") == -1:
                        continue
                    tracker_domian = StringUtils.get_url_netloc((tracker.get("url")))[1]
                    torrent_category = self.get_torrent_category(torrent, downloader_type)
                    torrent_tags = self.get_torrent_tags(torrent, downloader_type)
                    torrent_size = getattr(torrent, 'size', getattr(torrent, 'total_size', 0))

                    invalid_torrent_tuple_list.append(
                        (
                            torrent.name,
                            torrent_category,
                            torrent_tags,
                            torrent_size,
                            tracker_domian,
                            tracker.get("msg", ""),
                        )
                    )
                    if self._delete_invalid_torrents or self._label_only:
                        # 检查种子分类和标签是否排除
                        is_excluded = False
                        if torrent_category in exclude_categories:
                            is_excluded = True
                            invalid_torrents_exclude_categories.append(torrent)
                        torrent_labels = [
                            tag.strip() for tag in torrent_tags.split(",") if tag.strip()
                        ]
                        for label in torrent_labels:
                            if label in exclude_labels:
                                is_excluded = True
                                invalid_torrents_exclude_labels.append(torrent)
                        if not is_excluded:
                            # 获取种子hash
                            torrent_hash = self.get_torrent_hash(torrent, downloader_type)
                            if torrent_hash:
                                if self._label_only:
                                    # 仅标记
                                    self.set_torrent_label(downloader_obj, downloader_type, torrent_hash, torrent, self._label if self._label != "" else "无效做种")
                                else:
                                    # 只删除种子不删除文件，以防其它站点辅种
                                    downloader_obj.delete_torrents(False, torrent_hash)
                                # 标记已处理种子信息
                                deleted_torrent_tuple_list.append(
                                        (
                                            torrent.name,
                                            torrent_category,
                                            torrent_tags,
                                            torrent_size,
                                            tracker_domian,
                                            tracker.get("msg", ""),
                                        )
                                    )
                    break
            if len(invalid_torrent_tuple_list) > 0:
                invalid_msg = f"🔍 检测到 {len(invalid_torrent_tuple_list)} 个失效做种\n"
            else:
                invalid_msg = f"✅ 未发现失效做种，所有种子状态正常\n"

            if len(tracker_not_working_torrents) > 0:
                tracker_not_working_msg = f"⚠️ 检测到 {len(tracker_not_working_torrents)} 个 tracker 未工作的种子，请检查种子状态\n"
            else:
                tracker_not_working_msg = f"✅ 所有 tracker 工作正常\n"

            if self._label_only or self._delete_invalid_torrents:
                if self._label_only:
                    if len(deleted_torrent_tuple_list) > 0:
                        deleted_msg = f"🏷️ 已标记 {len(deleted_torrent_tuple_list)} 个失效种子\n"
                    else:
                        deleted_msg = f"✅ 无需标记任何种子\n"
                else:
                    if len(deleted_torrent_tuple_list) > 0:
                        deleted_msg = f"🗑️ 已删除 {len(deleted_torrent_tuple_list)} 个失效种子\n"
                    else:
                        deleted_msg = f"✅ 无需删除任何种子\n"

                if len(exclude_categories) != 0:
                    exclude_categories_msg = f"🏷️ 分类过滤：{len(invalid_torrents_exclude_categories)} 个失效种子因分类设置未处理，请手动检查\n"
                if len(exclude_labels) != 0:
                    exclude_labels_msg = f"🏷️ 标签过滤：{len(invalid_torrents_exclude_labels)} 个失效种子因标签设置未处理，请手动检查\n"
            for index in range(len(invalid_torrent_tuple_list)):
                torrent = invalid_torrent_tuple_list[index]
                invalid_msg += f"  {index + 1}. 📁 {torrent[0]}\n"
                invalid_msg += f"     📂 分类：{torrent[1]} | 🏷️ 标签：{torrent[2]} | 📏 大小：{StringUtils.str_filesize(torrent[3])}\n"
                invalid_msg += f"     🌐 Tracker：{torrent[4]} - {torrent[5]}\n"

            for index in range(len(tracker_not_working_torrents)):
                torrent_info = tracker_not_working_torrents[index]
                if isinstance(torrent_info, tuple):
                    # 新格式：(torrent, tracker_error_info)
                    torrent, tracker_error_info = torrent_info
                    torrent_category = self.get_torrent_category(torrent, downloader_type)
                    torrent_tags = self.get_torrent_tags(torrent, downloader_type)
                    torrent_size = getattr(torrent, 'size', getattr(torrent, 'total_size', 0))

                    tracker_not_working_msg += f"  {index + 1}. 📁 {torrent.name}\n"
                    tracker_not_working_msg += f"     📂 分类：{torrent_category} | 🏷️ 标签：{torrent_tags} | 📏 大小：{StringUtils.str_filesize(torrent_size)}\n"
                    if tracker_error_info:
                        tracker_not_working_msg += f"     🌐 Tracker错误：{', '.join(tracker_error_info)}\n"
                    else:
                        tracker_not_working_msg += f"     🌐 Tracker：未工作\n"
                else:
                    # 兼容旧格式：直接是torrent对象
                    torrent = torrent_info
                    torrent_size = getattr(torrent, 'size', getattr(torrent, 'total_size', 0))
                    tracker_not_working_msg += f"  {index + 1}. 📁 {torrent.name} (📏 {StringUtils.str_filesize(torrent_size)})\n"

            for index in range(len(invalid_torrents_exclude_categories)):
                torrent = invalid_torrents_exclude_categories[index]
                torrent_category = self.get_torrent_category(torrent, downloader_type)
                torrent_size = getattr(torrent, 'size', getattr(torrent, 'total_size', 0))
                exclude_categories_msg += f"  {index + 1}. 📁 {torrent.name} (📂 {torrent_category}, 📏 {StringUtils.str_filesize(torrent_size)})\n"

            for index in range(len(invalid_torrents_exclude_labels)):
                torrent = invalid_torrents_exclude_labels[index]
                torrent_tags = self.get_torrent_tags(torrent, downloader_type)
                torrent_size = getattr(torrent, 'size', getattr(torrent, 'total_size', 0))
                exclude_labels_msg += f"  {index + 1}. 📁 {torrent.name} (🏷️ {torrent_tags}, 📏 {StringUtils.str_filesize(torrent_size)})\n"

            for index in range(len(deleted_torrent_tuple_list)):
                torrent = deleted_torrent_tuple_list[index]
                deleted_msg += f"  {index + 1}. 📁 {torrent[0]}\n"
                deleted_msg += f"     📂 分类：{torrent[1]} | 🏷️ 标签：{torrent[2]} | 📏 大小：{StringUtils.str_filesize(torrent[3])}\n"
                deleted_msg += f"     🌐 Tracker：{torrent[4]} - {torrent[5]}\n"

            # 日志
            logger.info(invalid_msg)
            logger.info(tracker_not_working_msg)
            if self._delete_invalid_torrents:
                logger.info(deleted_msg)
                if len(exclude_categories) != 0:
                    logger.info(exclude_categories_msg)
                if len(exclude_labels) != 0:
                    logger.info(exclude_labels_msg)
            # 通知
            if self._notify:
                invalid_msg = invalid_msg.replace("_", "\_")
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=f"🧹 【清理无效做种】",
                    text=invalid_msg,
                )
                if self._notify_all:
                    tracker_not_working_msg = tracker_not_working_msg.replace("_", "\_")
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title=f"📊 【清理无效做种 - 详细信息】",
                        text=tracker_not_working_msg,
                    )
                if self._label_only or self._delete_invalid_torrents:
                    deleted_msg = deleted_msg.replace("_", "\_")
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title=f"🗑️ 【清理无效做种 - 删除结果】",
                        text=deleted_msg,
                    )
                    if self._notify_all:
                        exclude_categories_msg = exclude_categories_msg.replace("_", "\_")
                        self.post_message(
                            mtype=NotificationType.SiteMessage,
                            title=f"🏷️ 【清理无效做种 - 分类过滤】",
                            text=exclude_categories_msg,
                        )
                        exclude_labels_msg = exclude_labels_msg.replace("_", "\_")
                        self.post_message(
                            mtype=NotificationType.SiteMessage,
                            title=f"🏷️ 【清理无效做种 - 标签过滤】",
                            text=exclude_labels_msg,
                        )
            logger.info("检测无效做种任务结束")
            if self._detect_invalid_files:
                self.detect_invalid_files()

    def detect_invalid_files(self):
        logger.info("开始检测未做种的无效源文件")

        all_torrents = []

        for service in self.service_info.values():
            downloader_name = service.name
            downloader_obj = service.instance
            if not downloader_obj:
                logger.error(f"{self.LOG_TAG} 获取下载器失败 {downloader_name}")
                continue
            service_torrents = self.get_all_torrents(service)
            all_torrents += service_torrents

        source_path_map = {}
        source_paths = []
        total_size = 0
        deleted_file_cnt = 0
        exclude_key_words = (
            self._exclude_keywords.split("\n") if self._exclude_keywords else []
        )


        if not self._download_dirs:
            logger.error("未配置下载目录，无法检测未做种无效源文件")
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=f"⚠️ 【检测无效源文件】",
                text="未配置下载目录，无法检测未做种无效源文件",
            )
            return

        for path in self._download_dirs.split("\n"):
            if ":" not in path:
                continue
            parts = path.split(":")
            if len(parts) < 2:
                continue
            mp_path = parts[0].strip()
            # 支持一对多映射：MP路径:下载器路径1,下载器路径2,下载器路径3
            downloader_paths = [p.strip() for p in ":".join(parts[1:]).split(",") if p.strip()]

            if mp_path not in source_path_map:
                source_path_map[mp_path] = []
                source_paths.append(mp_path)
            source_path_map[mp_path].extend(downloader_paths)
        # 构建所有种子的内容路径集合
        content_path_set = set()
        path_extracted_count = 0     # 成功提取路径的种子数
        total_torrents_count = len(all_torrents)

        # 需要根据种子来源确定下载器类型，而不是假设所有种子来自同一个下载器
        for i, torrent in enumerate(all_torrents):
            if i % 100 == 0:  # 每100个种子输出一次进度
                logger.info(f"正在处理第 {i+1}/{total_torrents_count} 个种子")

            # 根据种子属性判断下载器类型 - 使用更宽松的检测条件
            downloader_type = "unknown"

            # 检查是否为qBittorrent种子
            if self.safe_hasattr(torrent, 'content_path', timeout=2):
                downloader_type = "qbittorrent"
            # 检查是否为Transmission种子 - 使用更多可能的属性组合
            elif self.safe_hasattr(torrent, 'downloadDir', timeout=2) or self.safe_hasattr(torrent, 'download_dir', timeout=2):
                downloader_type = "transmission"
            elif self.safe_hasattr(torrent, 'hashString', timeout=2):
                downloader_type = "transmission"
            elif self.safe_hasattr(torrent, 'trackerStats', timeout=2):
                downloader_type = "transmission"

            # 获取种子内容路径，兼容qBittorrent和Transmission
            content_path = None
            if downloader_type == "qbittorrent":
                content_path = self.safe_getattr(torrent, 'content_path', None, timeout=3)
            elif downloader_type == "transmission":
                # Transmission可能使用不同的属性名
                download_dir = self.safe_getattr(torrent, 'downloadDir', None, timeout=3)
                if download_dir is None:
                    download_dir = self.safe_getattr(torrent, 'download_dir', None, timeout=3)

                if download_dir is not None:
                    torrent_name = self.safe_getattr(torrent, 'name', None, timeout=2)
                    if torrent_name is not None:
                        content_path = f"{download_dir}/{torrent_name}"

            if content_path:
                content_path_set.add(content_path)
                path_extracted_count += 1

        logger.info(f"总种子数 {total_torrents_count}，成功提取路径的种子数: {path_extracted_count}，去重后的路径数: {len(content_path_set)}")

        filtered_files_count = 0  # 因时间不足被过滤的文件数

        message = "检测未做种无效源文件：\n"
        for source_path_str in source_paths:
            source_path = Path(source_path_str)
            # 判断source_path是否存在
            if not source_path.exists():
                logger.error(f"{source_path} 不存在，无法检测未做种无效源文件")
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=f"❌ 【检测无效源文件】",
                    text=f"路径 {source_path} 不存在，无法检测未做种无效源文件",
                )
                continue

            source_files = []
            # 获取source_path下的所有文件包括文件夹
            try:
                for file in source_path.iterdir():
                    source_files.append(file)
            except Exception as e:
                logger.error(f"遍历目录 {source_path} 失败: {e}")
                continue

            for i, source_file in enumerate(source_files):
                if i % 50 == 0:  # 每50个文件输出一次进度
                    logger.info(f"正在检测第 {i+1}/{len(source_files)} 个文件: {source_file.name}")
                skip = False
                for key_word in exclude_key_words:
                    if key_word in source_file.name:
                        skip = True
                        break
                if skip:
                    continue

                # 检查文件是否在任何一个映射的下载器路径中存在
                is_exist = False
                for downloader_path in source_path_map[source_path_str]:
                    # 将mp_path替换成对应的downloader_path
                    mapped_path = (str(source_file)).replace(source_path_str, downloader_path)

                    # 检查是否在种子内容路径中存在
                    for content_path in content_path_set:
                        if mapped_path in content_path:
                            is_exist = True
                            break
                    if is_exist:
                        break

                if not is_exist:
                    # 检查文件是否已经存在足够长时间
                    if not self.is_file_old_enough(source_file):
                        filtered_files_count += 1
                        continue

                    deleted_file_cnt += 1
                    message += f"{deleted_file_cnt}. {str(source_file)}\n"
                    total_size += self.get_size(source_file)
                    if self._delete_invalid_files:
                        if source_file.is_file():
                            source_file.unlink()
                        elif source_file.is_dir():
                            shutil.rmtree(source_file)

        # 添加时间筛选统计信息
        min_days = int(self._min_seeding_days) if self._min_seeding_days is not None else 0
        if min_days > 0 and filtered_files_count > 0:
            message += f"⏰ 时间筛选：过滤掉 {filtered_files_count} 个存在时间不足 {min_days} 天的文件\n"

        if deleted_file_cnt > 0:
            message += f"🔍 检测到 {deleted_file_cnt} 个未做种的无效源文件，共占用 {StringUtils.str_filesize(total_size)} 空间\n"
            if self._delete_invalid_files:
                message += f"🗑️ ***已删除无效源文件，释放 {StringUtils.str_filesize(total_size)} 空间！***\n"
            else:
                message += f"💡 提示：开启删除功能可自动清理这些文件\n"
        else:
            message += f"✅ 未发现无效源文件，所有文件都在正常做种中\n"
        logger.info(message)
        if self._notify:
            message = message.replace("_", "\_")
            # 根据结果选择不同的标题和表情
            if deleted_file_cnt > 0:
                if self._delete_invalid_files:
                    title = f"🧹 【清理无效源文件 - 已清理】"
                else:
                    title = f"🔍 【检测无效源文件 - 发现问题】"
            else:
                title = f"✅ 【检测无效源文件 - 一切正常】"

            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=title,
                text=message,
            )
        logger.info("检测无效源文件任务结束")

    def get_size(self, path: Path):
        total_size = 0
        if path.is_file():
            return path.stat().st_size
        # rglob 方法用于递归遍历所有文件和目录
        for entry in path.rglob("*"):
            if entry.is_file():
                total_size += entry.stat().st_size
        return total_size

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    # 基础设置
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
                                            "title": "🧹 清理无效做种插件",
                                            "text": "自动检测和清理下载器中的无效做种，支持qBittorrent和Transmission"
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    # 基本开关
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                            "color": "primary"
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次",
                                            "color": "success"
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify",
                                            "label": "开启通知",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "more_logs",
                                            "label": "详细日志",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 执行设置
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
                                            "label": "执行周期",
                                            "placeholder": "0 0 * * * (每天凌晨执行)",
                                            "prepend-inner-icon": "mdi-clock-outline"
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "multiple": True,
                                            "chips": True,
                                            "clearable": True,
                                            "model": "downloaders",
                                            "label": "选择下载器",
                                            "placeholder": "不选择则处理所有下载器",
                                            "prepend-inner-icon": "mdi-download",
                                            "items": [{"title": config.name, "value": config.name}
                                                      for config in self.downloader_helper.get_configs().values()]
                                        }
                                    }
                                ],
                            }
                        ],
                    },
                    # 种子处理设置
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
                                            "type": "warning",
                                            "variant": "tonal",
                                            "title": "⚠️ 种子处理设置",
                                            "text": "请谨慎开启删除功能，建议先使用仅标记模式测试"
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
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "label_only",
                                            "label": "仅标记模式",
                                            "color": "warning"
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
                                            "model": "delete_invalid_torrents",
                                            "label": "删除无效种子",
                                            "color": "error"
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "label",
                                            "label": "标记标签",
                                            "placeholder": "仅标记模式下的标签名称",
                                            "prepend-inner-icon": "mdi-tag"
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 源文件处理设置
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
                                            "title": "📁 源文件处理设置",
                                            "text": "检测和清理未做种的无效源文件"
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
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "detect_invalid_files",
                                            "label": "检测无效源文件",
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
                                            "model": "delete_invalid_files",
                                            "label": "删除无效源文件",
                                            "color": "error"
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "min_seeding_days",
                                            "label": "最小存在天数",
                                            "type": "number",
                                            "min": 0,
                                            "placeholder": "0=不限制",
                                            "prepend-inner-icon": "mdi-calendar"
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 目录映射配置
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "download_dirs",
                                            "label": "📂 下载目录映射",
                                            "rows": 4,
                                            "placeholder": "MP路径:下载器路径\n例如：/mp/download:/downloader/download\n一对多：/mp/download:/path1,/path2\n多个目录请换行",
                                            "prepend-inner-icon": "mdi-folder-multiple"
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    # 过滤设置
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
                                            "type": "secondary",
                                            "variant": "tonal",
                                            "title": "🔍 过滤设置",
                                            "text": "设置排除条件，避免误删重要文件"
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
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "exclude_keywords",
                                            "label": "🔤 排除关键字",
                                            "rows": 3,
                                            "placeholder": "源文件名包含这些关键字将被跳过\n每行一个关键字",
                                            "prepend-inner-icon": "mdi-text-search"
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "exclude_categories",
                                            "label": "📂 排除分类",
                                            "rows": 3,
                                            "placeholder": "这些分类的种子将被跳过\n每行一个分类名",
                                            "prepend-inner-icon": "mdi-folder-outline"
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "exclude_labels",
                                            "label": "🏷️ 排除标签",
                                            "rows": 3,
                                            "placeholder": "这些标签的种子将被跳过\n每行一个标签名",
                                            "prepend-inner-icon": "mdi-tag-outline"
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 自定义错误消息
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "custom_error_msg",
                                            "label": "⚠️ 自定义错误消息",
                                            "rows": 4,
                                            "placeholder": "添加自定义的tracker错误消息\n例如：Could not connect to tracker\n每行一个错误消息",
                                            "prepend-inner-icon": "mdi-alert-circle-outline"
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
                                            "model": "notify_all",
                                            "label": "详细通知",
                                        },
                                    },
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "默认错误消息包括：\n• torrent not registered\n• torrent banned\n• Torrent not exists\n等常见错误",
                                            "class": "mt-4"
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    # 重要提示
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
                                            "type": "error",
                                            "variant": "tonal",
                                            "title": "🚨 重要提示",
                                            "text": "• 建议先使用「仅标记模式」测试，确认无误后再开启删除功能\n• 删除操作不可逆，请谨慎使用\n• 支持一对多目录映射：/mp/path:/dl1,/dl2,/dl3"
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
            "notify": False,
            "download_dirs": "",
            "delete_invalid_torrents": False,
            "delete_invalid_files": False,
            "detect_invalid_files": False,
            "notify_all": False,
            "onlyonce": False,
            "cron": "0 0 * * *",
            "label_only": False,
            "label": "",
            "more_logs": False,
            "min_seeding_days": 0,
        }

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e))
