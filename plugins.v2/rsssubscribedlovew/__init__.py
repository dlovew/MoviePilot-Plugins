import datetime
import re
import traceback
from pathlib import Path
from threading import Lock
from typing import Optional, Any, List, Dict, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import schemas
from app.chain.download import DownloadChain
from app.chain.subscribe import SubscribeChain
from app.core.config import settings
from app.core.context import MediaInfo, TorrentInfo, Context
from app.core.metainfo import MetaInfo
from app.core.meta.streamingplatform import StreamingPlatforms
from app.db.site_oper import SiteOper
from app.helper.rss import RssHelper
from app.utils.tokens import Tokens
from urllib.parse import urlparse
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import ExistMediaInfo
from app.schemas.types import SystemConfigKey, MediaType, NotificationType

lock = Lock()


class RssSubscribedlovew(_PluginBase):
    # 插件名称
    plugin_name = "自定义订阅番剧魔改版 -dlovew"
    # 插件描述
    plugin_desc = "定时刷新RSS报文，识别内容后添加订阅或直接下载。"
    # 插件图标
    plugin_icon = "rss.png"
    # 插件版本
    plugin_version = "2.2"
    # 插件作者
    plugin_author = "dlovew"
    # 作者主页
    author_url = "https://github.com/dlovew"
    # 插件配置项ID前缀
    plugin_config_prefix = "rssubscribedlovew_"
    # 加载顺序
    plugin_order = 19
    # 可使用的用户级别
    auth_level = 2

    # 私有变量
    _scheduler: Optional[BackgroundScheduler] = None
    _cache_path: Optional[Path] = None

    # 配置属性
    _enabled: bool = False
    _cron: str = ""
    _notify: bool = False
    _onlyonce: bool = False
    _address: str = ""
    _include: str = ""
    _exclude: str = ""
    _proxy: bool = False
    _filter: bool = False
    _clear: bool = False
    _clearflag: bool = False
    _action: str = "subscribe"
    _save_path: str = ""
    _size_range: str = ""

    def init_plugin(self, config: dict = None):

        # 停止现有任务
        self.stop_service()

        # 配置
        if config:
            self.__validate_and_fix_config(config=config)
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._notify = config.get("notify")
            self._onlyonce = config.get("onlyonce")
            self._address = config.get("address")
            self._include = config.get("include")
            self._exclude = config.get("exclude")
            self._proxy = config.get("proxy")
            self._filter = config.get("filter")
            self._clear = config.get("clear")
            self._action = config.get("action")
            self._save_path = config.get("save_path")
            self._size_range = config.get("size_range")

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            logger.info(f"自定义订阅服务启动，立即运行一次")
            self._scheduler.add_job(func=self.check, trigger='date',
                                    run_date=datetime.datetime.now(
                                        tz=pytz.timezone(settings.TZ)) + datetime.timedelta(seconds=3)
                                    )

            # 启动任务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

        if self._onlyonce or self._clear:
            # 关闭一次性开关
            self._onlyonce = False
            # 记录清理缓存设置
            self._clearflag = self._clear
            # 关闭清理缓存开关
            self._clear = False
            # 保存设置
            self.__update_config()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API
        [{
            "path": "/xx",
            "endpoint": self.xxx,
            "methods": ["GET", "POST"],
            "summary": "API说明"
        }]
        """
        return [
            {
                "path": "/delete_history",
                "endpoint": self.delete_history,
                "methods": ["GET"],
                "summary": "删除自定义订阅历史记录"
            }
        ]

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
            return [{
                "id": "RssSubscribe",
                "name": "自定义订阅服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.check,
                "kwargs": {}
            }]
        elif self._enabled:
            return [{
                "id": "RssSubscribe",
                "name": "自定义订阅服务",
                "trigger": "interval",
                "func": self.check,
                "kwargs": {"minutes": 30}
            }]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '发送通知',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式，留空自动'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'action',
                                            'label': '动作',
                                            'items': [
                                                {'title': '订阅', 'value': 'subscribe'},
                                                {'title': '下载', 'value': 'download'}
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'address',
                                            'label': 'RSS地址',
                                            'rows': 3,
                                            'placeholder': '每行一个RSS地址'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                        'model': 'include',
                                        'label': '包含',
                                        'placeholder': '支持正则表达式'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'exclude',
                                            'label': '排除',
                                            'placeholder': '支持正则表达式'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'size_range',
                                            'label': '种子大小(GB)',
                                            'placeholder': '如：3 或 3-5'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'save_path',
                                            'label': '保存目录',
                                            'placeholder': '下载时有效，留空自动'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'proxy',
                                            'label': '使用代理服务器',
                                        }
                                    }
                                ]
                            }, {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4,
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'filter',
                                            'label': '使用订阅优先级规则',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'clear',
                                            'label': '清理历史记录',
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "notify": True,
            "onlyonce": False,
            "cron": "*/30 * * * *",
            "address": "",
            "include": "",
            "exclude": "",
            "proxy": False,
            "clear": False,
            "filter": False,
            "action": "subscribe",
            "save_path": "",
            "size_range": ""
        }

    def get_page(self) -> List[dict]:
        """
        拼装插件详情页面，需要返回页面配置，同时附带数据
        """
        # 查询同步详情
        historys = self.get_data('history')
        if not historys:
            return [
                {
                    'component': 'div',
                    'text': '暂无数据',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]
        # 数据按时间降序排序
        historys = sorted(historys, key=lambda x: x.get('time'), reverse=True)
        # 拼装页面
        contents = []
        for history in historys:
            title = history.get("title")
            poster = history.get("poster")
            mtype = history.get("type")
            time_str = history.get("time")
            contents.append(
                {
                    'component': 'VCard',
                    'content': [
                        {
                            "component": "VDialogCloseBtn",
                            "props": {
                                'innerClass': 'absolute top-0 right-0',
                            },
                            'events': {
                                'click': {
                                    'api': 'plugin/RssSubscribe/delete_history',
                                    'method': 'get',
                                    'params': {
                                        'key': title,
                                        'apikey': settings.API_TOKEN
                                    }
                                }
                            },
                        },
                        {
                            'component': 'div',
                            'props': {
                                'class': 'd-flex justify-space-start flex-nowrap flex-row',
                            },
                            'content': [
                                {
                                    'component': 'div',
                                    'content': [
                                        {
                                            'component': 'VImg',
                                            'props': {
                                                'src': poster,
                                                'height': 120,
                                                'width': 80,
                                                'aspect-ratio': '2/3',
                                                'class': 'object-cover shadow ring-gray-500',
                                                'cover': True
                                            }
                                        }
                                    ]
                                },
                                {
                                    'component': 'div',
                                    'content': [
                                        {
                                            'component': 'VCardTitle',
                                            'props': {
                                                'class': 'pa-1 pe-5 break-words whitespace-break-spaces'
                                            },
                                            'text': title
                                        },
                                        {
                                            'component': 'VCardText',
                                            'props': {
                                                'class': 'pa-0 px-2'
                                            },
                                            'text': f'类型：{mtype}'
                                        },
                                        {
                                            'component': 'VCardText',
                                            'props': {
                                                'class': 'pa-0 px-2'
                                            },
                                            'text': f'时间：{time_str}'
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            )

        return [
            {
                'component': 'div',
                'props': {
                    'class': 'grid gap-3 grid-info-card',
                },
                'content': contents
            }
        ]

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

    def delete_history(self, key: str, apikey: str):
        """
        删除同步历史记录
        """
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")
        # 历史记录
        historys = self.get_data('history')
        if not historys:
            return schemas.Response(success=False, message="未找到历史记录")
        # 删除指定记录
        historys = [h for h in historys if h.get("title") != key]
        self.save_data('history', historys)
        return schemas.Response(success=True, message="删除成功")

    def __update_config(self):
        """
        更新设置
        """
        self.update_config({
            "enabled": self._enabled,
            "notify": self._notify,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "address": self._address,
            "include": self._include,
            "exclude": self._exclude,
            "proxy": self._proxy,
            "clear": self._clear,
            "filter": self._filter,
            "action": self._action,
            "save_path": self._save_path,
            "size_range": self._size_range
        })

    def check(self):
        """
        通过用户RSS同步豆瓣想看数据
        """
        if not self._address:
            return
        # 读取历史记录
        if self._clearflag:
            history = []
        else:
            history: List[dict] = self.get_data('history') or []
        downloadchain = DownloadChain()
        subscribechain = SubscribeChain()
        for url in self._address.split("\n"):
            # 处理每一个RSS链接
            if not url:
                continue
            logger.info(f"开始刷新RSS：{url} ...")
            results = RssHelper().parse(url, proxy=self._proxy)
            if not results:
                logger.error(f"未获取到RSS数据：{url}")
                return
            # 过滤规则
            filter_groups = self.systemconfig.get(SystemConfigKey.SubscribeFilterRuleGroups)
            # 解析数据
            for result in results:
                try:
                    title = result.get("title")
                    description = result.get("description")
                    enclosure = result.get("enclosure")
                    link = result.get("link")
                    size = result.get("size")
                    pubdate: datetime.datetime = result.get("pubdate")
                    # 检查是否处理过
                    if not title or title in [h.get("key") for h in history]:
                        continue
                    # 检查规则
                    if self._include and not re.search(r"%s" % self._include,
                                                       f"{title} {description}", re.IGNORECASE):
                        logger.info(f"{title} - {description} 不符合包含规则")
                        continue
                    if self._exclude and re.search(r"%s" % self._exclude,
                                                   f"{title} {description}", re.IGNORECASE):
                        logger.info(f"{title} - {description} 不符合排除规则")
                        continue
                    if self._size_range:
                        if not size:
                            logger.info(f"{title} - 种子大小缺失，跳过")
                            continue
                        sizes = [float(_size) * 1024 ** 3 for _size in self._size_range.split("-")]
                        if len(sizes) == 1 and float(size) < sizes[0]:
                            logger.info(f"{title} - 种子大小不符合条件")
                            continue
                        elif len(sizes) > 1 and not sizes[0] <= float(size) <= sizes[1]:
                            logger.info(f"{title} - 种子大小不在指定范围")
                            continue
                    # 识别媒体信息
                    meta = MetaInfo(title=title, subtitle=description)
                    if not meta.name:
                        logger.warn(f"{title} 未识别到有效数据")
                        # 要求1：无法识别，直接推送通知（资源标题），并记录历史避免重复通知
                        self.__notify_unknown(title, history)
                        continue
                    mediainfo: MediaInfo = self.chain.recognize_media(meta=meta)
                    if not mediainfo:
                        logger.warn(f'未识别到媒体信息，标题：{title}')
                        # 要求1：无法识别，直接推送通知（资源标题），并记录历史避免重复通知
                        self.__notify_unknown(title, history)
                        continue
                    # 种子
                    torrentinfo = TorrentInfo(
                        title=title,
                        description=description,
                        enclosure=enclosure,
                        page_url=link,
                        size=size,
                        pubdate=pubdate.strftime("%Y-%m-%d %H:%M:%S") if pubdate else None,
                        site_proxy=self._proxy,
                    )
                    # 过滤种子
                    if self._filter:
                        result = self.chain.filter_torrents(
                            rule_groups=filter_groups,
                            torrent_list=[torrentinfo],
                            mediainfo=mediainfo
                        )
                        if not result:
                            logger.info(f"{title} {description} 不匹配过滤规则")
                            continue
                    # 媒体库已存在的剧集
                    exist_info: Optional[ExistMediaInfo] = self.chain.media_exists(mediainfo=mediainfo)
                    if mediainfo.type == MediaType.TV:
                        if exist_info:
                            exist_season = exist_info.seasons
                            if exist_season:
                                exist_episodes = exist_season.get(meta.begin_season)
                                if exist_episodes and set(meta.episode_list).issubset(set(exist_episodes)):
                                    logger.info(f'{mediainfo.title_year} {meta.season_episode} 己存在')
                                    continue
                    elif exist_info:
                        # 电影已存在
                        logger.info(f'{mediainfo.title_year} 己存在')
                        continue
                    # ===== 流媒体平台分支（要求2 / 要求3 / 要求4 + 补充3）=====
                    sp = self.__get_streaming_platforms(title, meta)
                    is_iq = 'IQ' in sp
                    is_linetv = 'LINETV' in sp
                    is_2160p = self.__is_2160p(meta)
                    if is_iq and not is_2160p:
                        # 补充3：IQ 但非 2160P，完全不处理、不通知，静默跳过（记历史防重复判断）
                        logger.info(f"{title} 为 IQ 但非 2160P，跳过")
                    elif is_iq and is_2160p:
                        # 要求2：IQ 且 2160P，直接订阅
                        subflag = subscribechain.exists(mediainfo=mediainfo, meta=meta)
                        if not subflag:
                            self.__add_strong_subscribe(subscribechain=subscribechain,
                                                        meta=meta,
                                                        mediainfo=mediainfo,
                                                        rss_url=url,
                                                        platform='IQ')
                        else:
                            logger.info(f'{mediainfo.title_year} {meta.season} 正在订阅中')
                    elif is_linetv:
                        # 要求3：非 IQ 且为 LINETV，先判断订阅存在再订阅
                        subflag = subscribechain.exists(mediainfo=mediainfo, meta=meta)
                        if not subflag:
                            self.__add_strong_subscribe(subscribechain=subscribechain,
                                                        meta=meta,
                                                        mediainfo=mediainfo,
                                                        rss_url=url,
                                                        platform='LINETV')
                        else:
                            logger.info(f'{mediainfo.title_year} {meta.season} 正在订阅中')
                    else:
                        # 要求4：既非 IQ 也非 LINETV，直接发通知（媒体名+季）
                        season_info = self.__season_label(meta)
                        notify_msg = f"{mediainfo.title_year} {season_info}".strip()
                        logger.info(f"{title} 非 IQ/LINETV 资源，发送通知：{notify_msg}")
                        if self._notify:
                            self.post_message(
                                mtype=NotificationType.Plugin,
                                title="自定义订阅",
                                text=notify_msg
                            )
                    # 统一存储历史记录（订阅与通知均记录，避免重复处理/通知）
                    history.append({
                        "title": f"{mediainfo.title} {self.__season_label(meta)}",
                        "key": f"{title}",
                        "type": mediainfo.type.value,
                        "year": mediainfo.year,
                        "poster": mediainfo.get_poster_image(),
                        "overview": mediainfo.overview,
                        "tmdbid": mediainfo.tmdb_id,
                        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                except Exception as err:
                    logger.error(f'刷新RSS数据出错：{str(err)} - {traceback.format_exc()}')
            logger.info(f"RSS {url} 刷新完成")
        # 保存历史记录
        self.save_data('history', history)
        # 缓存只清理一次
        self._clearflag = False

    def __log_and_notify_error(self, message):
        """
        记录错误日志并发送系统通知
        """
        logger.error(message)
        if self._notify:
            self.post_message(
                mtype=NotificationType.Plugin,
                title="自定义订阅",
                text=message
            )

    def __notify_unknown(self, title: str, history: List[dict]):
        """
        资源无法识别媒体时：推送系统通知（内容为资源标题）并记录历史，避免重复通知
        """
        self.systemmessage.put(title, title="自定义订阅")
        history.append({
            "title": title,
            "key": title,
            "type": "",
            "year": "",
            "poster": "",
            "overview": "",
            "tmdbid": "",
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    def __validate_and_fix_config(self, config: dict = None) -> bool:
        """
        检查并修正配置值
        """
        size_range = config.get("size_range")
        if size_range and not self.__is_number_or_range(str(size_range)):
            self.__log_and_notify_error(f"自定义订阅出错，种子大小设置错误：{size_range}")
            config["size_range"] = None
            return False
        return True

    @staticmethod
    def __is_number_or_range(value):
        """
        检查字符串是否表示单个数字或数字范围（如'5', '5.5', '5-10' 或 '5.5-10.2'）
        """
        return bool(re.match(r"^\d+(\.\d+)?(-\d+(\.\d+)?)?$", value))

    def __get_streaming_platforms(self, title: str, meta) -> set:
        """
        提取资源标题/识别结果中的流媒体平台标识集合（大写）。
        优先使用 MetaInfo.web_source 与 StreamingPlatforms 识别，
        并对用户关注的 IQ / LINETV 做显式兜底匹配（二者可能不在内置列表中）。
        """
        platforms = set()
        # 1. MetaInfo 识别出的流媒体来源
        web_source = getattr(meta, "web_source", None)
        if web_source:
            platforms.add(str(web_source).upper())
        # 2. 通过 Tokens + StreamingPlatforms 识别标题中的流媒体平台简称
        try:
            for token in Tokens(title).tokens:
                if StreamingPlatforms().is_streaming_platform(token):
                    platforms.add(token.upper())
        except Exception as err:
            logger.debug(f"流媒体平台识别出错：{str(err)}")
        # 3. 显式兜底：用户明确资源标题中平台为确定写法
        #    IQ = 爱奇艺（标题中即 "IQ"）；LINETV = LINE TV
        upper_title = title.upper()
        if re.search(r"\bIQ\b", upper_title):
            platforms.add("IQ")
        if "LINETV" in upper_title or re.search(r"LINE\s*TV", upper_title):
            platforms.add("LINETV")
        return platforms

    @staticmethod
    def __is_2160p(meta) -> bool:
        """判断识别分辨率是否为 2160P / 4K"""
        pix = getattr(meta, "resource_pix", None)
        if not pix:
            return False
        pix = str(pix).lower()
        return "2160" in pix or "4k" in pix

    @staticmethod
    def __build_include(platform: str, team: str = None) -> str:
        """构造订阅 include 正则：流媒体平台 + 制作组 的正向预查组合（参考油猴插件）"""
        parts = [f"(?=.*{platform})"]
        if team:
            parts.append(f"(?=.*{team})")
        return "".join(parts)

    @staticmethod
    def __season_label(meta) -> str:
        """返回规范化的季标识 Sxx，兼容 meta.season 直接返回 'S01' 字符串的版本"""
        season = getattr(meta, "begin_season", None) or getattr(meta, "season", None)
        if not season:
            return ""
        if isinstance(season, str):
            m = re.search(r"(\d+)", season)
            season = int(m.group(1)) if m else None
        if season is None:
            return ""
        try:
            return f"S{int(season):02d}"
        except (TypeError, ValueError):
            return f"S{season}"

    @staticmethod
    def __parse_pix(pix) -> Optional[str]:
        """将分辨率规整为订阅正则（参考 SubscribeGroupMod）"""
        if not pix:
            return None
        pix = str(pix).lower()
        if "2160" in pix or "4k" in pix:
            return "4K|2160p|x2160"
        if "1080" in pix:
            return "1080[pi]|x1080"
        if "720" in pix:
            return "720[pi]|x720"
        if "480" in pix:
            return "480[pi]|x480"
        return str(pix)

    @staticmethod
    def __parse_type(type_) -> Optional[str]:
        """将制作质量规整为订阅正则（参考 SubscribeGroupMod）"""
        if not type_:
            return None
        type_ = str(type_).lower()
        if "remux" in type_:
            return "Remux"
        if "web" in type_:
            return "WEB-?DL|WEB-?RIP"
        if "blu" in type_ or "bluray" in type_:
            return "Blu-?Ray"
        if "265" in type_ or "hevc" in type_:
            return "[Hx].?265|HEVC"
        if "264" in type_ or "avc" in type_:
            return "[Hx].?264|AVC"
        return str(type_)

    @staticmethod
    def __parse_effect(effect) -> Optional[str]:
        """将特效规整为订阅正则（参考 SubscribeGroupMod）"""
        if not effect:
            return None
        effect = str(effect).lower()
        if "dolby" in effect or "dovi" in effect or effect == "dv":
            return r"Dolby[\s.]+Vision|DOVI|DV"
        if "hdr" in effect:
            return r"[\s.]+HDR[\s.]+|HDR10|HDR10\+"
        if "atmos" in effect:
            return "Atmos"
        return str(effect)

    def __get_site_ids(self, rss_url: str) -> List[int]:
        """根据 RSS 地址域名匹配已启用站点，返回站点 ID 列表（用于订阅 sites 参数）"""
        try:
            netloc = urlparse(rss_url).netloc.lower()
        except Exception:
            return []
        if not netloc:
            return []
        try:
            sites = SiteOper().list_active()
        except Exception as err:
            logger.debug(f"获取站点列表失败：{str(err)}")
            return []
        ids = []
        for site in sites:
            domain = getattr(site, "domain", None)
            if not domain:
                continue
            domain = str(domain).lower()
            if domain and (netloc == domain or netloc.endswith(domain) or domain in netloc):
                ids.append(site.id)
        return ids

    def __add_strong_subscribe(self, subscribechain, meta, mediainfo, rss_url: str, platform: str):
        """
        添加“强订阅”：参考油猴插件，传递站点、流媒体平台、分辨率、制作组等精细参数。
        platform: 'IQ' 或 'LINETV'
        """
        site_ids = self.__get_site_ids(rss_url)
        team = getattr(meta, "resource_team", None)
        include = self.__build_include(platform, team)
        resolution = self.__parse_pix(getattr(meta, "resource_pix", None))
        quality = self.__parse_type(getattr(meta, "resource_type", None))
        effect = self.__parse_effect(getattr(meta, "resource_effect", None))
        # 仅在对应字段存在时透传，避免 None 覆盖默认配置
        kwargs = {
            "include": include,
            "sites": site_ids,
            "username": "RSS订阅",
            "exist_ok": True,
        }
        if resolution:
            kwargs["resolution"] = resolution
        if quality:
            kwargs["quality"] = quality
        if effect:
            kwargs["effect"] = effect
        subscribechain.add(
            title=mediainfo.title,
            year=mediainfo.year,
            mtype=mediainfo.type,
            tmdbid=mediainfo.tmdb_id,
            season=meta.begin_season,
            **kwargs
        )
        logger.info(f"添加强订阅：{mediainfo.title_year} 平台={platform} "
                    f"制作组={team} 站点={site_ids} include={include} "
                    f"分辨率={resolution} 质量={quality} 特效={effect}")
