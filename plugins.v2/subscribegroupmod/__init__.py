import json
import re
import time
from typing import Any, List, Dict, Tuple

from app.core.event import eventmanager, Event
from app.core.meta import MetaVideo
from app.core.meta.streamingplatform import StreamingPlatforms
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.site_oper import SiteOper
from app.db.subscribe_oper import SubscribeOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, SystemConfigKey, MediaType
from app.utils.tokens import Tokens


class SubscribeGroupMod(_PluginBase):
    # 插件名称
    plugin_name = "订阅规则自动填充魔改版 -dlovew"
    # 插件描述
    plugin_desc = "订阅时/下载后自动填充官组、流媒体平台等；支持二级分类自定义规则。"
    # 插件图标
    plugin_icon = "teamwork.png"
    # 插件版本
    plugin_version = "2.9.1"
    # 插件作者
    plugin_author = "dlovew"
    # 作者主页
    author_url = "https://github.com/thsrite"
    # 插件配置项ID前缀
    plugin_config_prefix = "subscribegroupmod_"
    # 加载顺序
    plugin_order = 26
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled: bool = False
    _category: bool = False
    _clear = False
    _clear_handle = False
    _update_details = []
    _update_confs = None
    _subscribe_confs = {}
    _subscribeoper = None
    _downloadhistoryoper = None
    _siteoper = None

    def init_plugin(self, config: dict = None):
        self._downloadhistoryoper = DownloadHistoryOper()
        self._subscribeoper = SubscribeOper()
        self._siteoper = SiteOper()

        if config:
            self._enabled = config.get("enabled")
            self._category = config.get("category")
            self._clear = config.get("clear")
            self._clear_handle = config.get("clear_handle")
            self._update_details = config.get("update_details") or []
            self._update_confs = config.get("update_confs")

            if self._update_confs:
                active_sites = self._siteoper.list_active()
                for confs in str(self._update_confs).split("\n"):
                    category = None
                    resolution = None
                    quality = None
                    effect = None
                    include = None
                    exclude = None
                    savepath = None
                    sites = []
                    filter_groups = []
                    for conf in str(confs).split("#"):
                        if ":" in conf:
                            k = conf.split(":")[0]
                            v = ":".join(conf.split(":")[1:])
                            if k == "category":
                                category = v
                            if k == "resolution":
                                resolution = v
                            if k == "quality":
                                quality = v
                            if k == "effect":
                                effect = v
                            if k == "include":
                                include = v
                            if k == "exclude":
                                exclude = v
                            if k == "savepath":
                                savepath = v
                            if k == "sites":
                                for site_name in str(v).split(","):
                                    for active_site in active_sites:
                                        if str(site_name) == str(active_site.name):
                                            sites.append(active_site.id)
                                            break
                            if k == "filter_groups":
                                filter_groups = [filter_group for filter_group in str(v).split(",")]

                    if category:
                        for c in str(category).split(","):
                            self._subscribe_confs[c] = {
                                'resolution': resolution,
                                'quality': quality,
                                'effect': effect,
                                'include': include,
                                'exclude': exclude,
                                'savepath': savepath,
                                'sites': sites,
                                'filter_groups': filter_groups
                            }
                logger.info(f"获取到二级分类自定义配置 {len(self._subscribe_confs.keys())} 个")
            else:
                self._subscribe_confs = {}

            if self._clear_handle:
                self.del_data(key="history_handle")
                self._clear_handle = False
                self.__update_config()
                logger.info("已处理历史清理完成")

            if self._clear:
                self.del_data(key="history")
                self._clear = False
                self.__update_config()
                logger.info("历史记录清理完成")

    def __update_config(self):
        self.update_config({
            "enabled": self._enabled,
            "category": self._category,
            "clear": self._clear,
            "clear_handle": self._clear_handle,
            "update_details": self._update_details,
            "update_confs": self._update_confs,
        })

    @eventmanager.register(EventType.SubscribeAdded)
    def subscribe_notice(self, event: Event = None):
        """
        添加订阅时：二级分类自定义填充 + 流媒体平台自动填充
        """
        if not event:
            logger.error("订阅事件数据为空")
            return

        if not self._category and "流媒体平台" not in self._update_details:
            return

        if len(self._subscribe_confs.keys()) == 0 and "流媒体平台" not in self._update_details:
            return

        event_data = event.event_data
        if not event_data or not event_data.get("subscribe_id") or not event_data.get("mediainfo"):
            logger.error(f"订阅事件数据不完整 {event_data}")
            return

        sid = event_data.get("subscribe_id")
        mediainfo = event_data.get("mediainfo")
        category = mediainfo.get("category")

        # 如果没有 category，尝试通过媒体信息重新识别
        if not category:
            media_info = self.chain.recognize_media(mtype=MediaType(mediainfo.get("type")),
                                                    tmdbid=mediainfo.get("tmdb_id"))
            if media_info and media_info.category:
                category = media_info.category
                logger.info(f"订阅ID:{sid} 二级分类:{category} 已通过媒体信息识别")

        update_dict = {}

        # 二级分类自定义填充
        if self._category and category and category in self._subscribe_confs:
            category_conf = self._subscribe_confs.get(category)
            logger.info(f"订阅记录:{mediainfo.get('title')} 二级分类:{category} 自定义配置:{category_conf}")

            if category_conf.get('include'):
                update_dict['include'] = category_conf.get('include')
            if category_conf.get('exclude'):
                update_dict['exclude'] = category_conf.get('exclude')
            if category_conf.get('sites'):
                update_dict['sites'] = category_conf.get('sites')
            if category_conf.get('filter_groups'):
                update_dict['filter_groups'] = category_conf.get('filter_groups')
            if category_conf.get('resolution'):
                update_dict['resolution'] = self.__parse_pix(category_conf.get('resolution'))
            if category_conf.get('quality'):
                update_dict['quality'] = self.__parse_type(category_conf.get('quality'))
            if category_conf.get('effect'):
                update_dict['effect'] = self.__parse_effect(category_conf.get('effect'))
            if category_conf.get('savepath'):
                subscribe = self._subscribeoper.get(sid)
                if subscribe and '{name}' in category_conf.get('savepath'):
                    savepath = category_conf.get('savepath').replace('{name}', f"{subscribe.name} ({subscribe.year})")
                    update_dict['save_path'] = savepath
                else:
                    update_dict['save_path'] = category_conf.get('savepath')

        # 流媒体平台填充（新增）
        if "流媒体平台" in self._update_details:
            title = mediainfo.get("title")
            if title:
                web_source = self._get_streaming_platform_from_title(title)
                if web_source:
                    current_include = update_dict.get('include') or ""
                    if current_include:
                        update_dict['include'] = f"(?=.*{web_source})" + current_include
                    else:
                        update_dict['include'] = f"(?=.*{web_source})"
                    logger.info(f"订阅ID:{sid} 已从标题中提取流媒体平台: {web_source}")
                else:
                    logger.info(f"订阅ID:{sid} 标题中未识别到流媒体平台")

        # 应用更新
        if update_dict:
            self._subscribeoper.update(sid, update_dict)
            logger.info(f"订阅记录 {mediainfo.get('title')} 填充成功\n{update_dict}")

            # 保存历史
            history = self.get_data('history') or []
            history.append({
                'name': mediainfo.get('title'),
                'type': f'订阅自动填充 (二级分类:{category})',
                'content': json.dumps(update_dict, ensure_ascii=False),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
            })
            self.save_data(key="history", value=history)
        else:
            logger.info(f"订阅ID:{sid} 无需更新")

    @eventmanager.register(EventType.DownloadAdded)
    def download_notice(self, event: Event = None):
        """
        添加下载时填充订阅制作组等信息（需开启 enabled）
        """
        if not event or not self._enabled:
            return
        if len(self._update_details) == 0:
            return

        event_data = event.event_data
        if not event_data or not event_data.get("hash") or not event_data.get("context"):
            return
        download_hash = event_data.get("hash")
        download_history = self._downloadhistoryoper.get_by_hash(download_hash)
        if not download_history:
            return

        history_handle: List[str] = self.get_data('history_handle') or []
        if f"{download_history.type}:{download_history.tmdbid}" in history_handle:
            return
        if download_history.type != '电视剧':
            return

        subscribes = self._subscribeoper.list_by_tmdbid(
            tmdbid=download_history.tmdbid,
            season=int(download_history.seasons.replace('S', ''))
            if download_history.seasons and download_history.seasons.count('-') == 0 else None
        )
        if not subscribes:
            return

        context = event_data.get("context")
        _torrent = context.torrent_info
        _meta = context.meta_info

        for subscribe in subscribes:
            if subscribe.type != '电视剧':
                continue
            update_dict = {}
            if "分辨率" in self._update_details and not subscribe.resolution:
                resource_pix = _meta.resource_pix if _meta else None
                if resource_pix:
                    resource_pix = self.__parse_pix(resource_pix)
                    if resource_pix:
                        update_dict['resolution'] = resource_pix
            if "资源质量" in self._update_details and not subscribe.quality:
                resource_type = _meta.resource_type if _meta else None
                if resource_type:
                    resource_type = self.__parse_type(resource_type)
                    if resource_type:
                        update_dict['quality'] = resource_type
            if "特效" in self._update_details and not subscribe.effect:
                resource_effect = _meta.resource_effect if _meta else None
                if resource_effect:
                    resource_effect = self.__parse_effect(resource_effect)
                    if resource_effect:
                        update_dict['effect'] = resource_effect
            if "制作组" in self._update_details and not subscribe.include:
                resource_team = _meta.resource_team if _meta else None
                customization = _meta.customization if _meta else None
                if resource_team and customization:
                    resource_team = f"{customization}.+{resource_team}"
                if not resource_team and customization:
                    resource_team = customization
                if resource_team:
                    update_dict['include'] = f"(?=.*{resource_team})"
            if "流媒体平台" in self._update_details and isinstance(_meta, MetaVideo):
                m: MetaVideo = _meta
                web_source = self._get_streaming_platform_from_title(m.title if m else None)
                if web_source:
                    if not subscribe.include:
                        update_dict['include'] = f"(?=.*{web_source})"
                    else:
                        update_dict['include'] += f"(?=.*{web_source})"
            if "站点" in self._update_details and (not subscribe.sites or len(subscribe.sites) == 0):
                rss_sites = self.systemconfig.get(SystemConfigKey.RssSites) or []
                if _torrent and _torrent.site and int(_torrent.site) in rss_sites:
                    update_dict['sites'] = [_torrent.site]

            if update_dict:
                self._subscribeoper.update(subscribe.id, update_dict)
                logger.info(f"订阅记录:{subscribe.name} 下载时填充成功\n{update_dict}")
                history = self.get_data('history') or []
                history.append({
                    'name': subscribe.name,
                    'type': '下载触发填充',
                    'content': json.dumps(update_dict, ensure_ascii=False),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
                })
                self.save_data(key="history", value=history)
                history_handle.append(f"{download_history.type}:{download_history.tmdbid}")
                self.save_data('history_handle', history_handle)

    # 辅助方法
    def __parse_pix(self, resource_pix):
        if re.match(r"1080[pi]|x1080", resource_pix, re.IGNORECASE):
            return "1080[pi]|x1080"
        if re.match(r"4K|2160p|x2160", resource_pix, re.IGNORECASE):
            return "4K|2160p|x2160"
        if re.match(r"720[pi]|x720", resource_pix, re.IGNORECASE):
            return "720[pi]|x720"
        return resource_pix

    def __parse_type(self, resource_type):
        if re.match(r"Blu-?Ray.+VC-?1|Blu-?Ray.+AVC|UHD.+blu-?ray.+HEVC|MiniBD", resource_type, re.IGNORECASE):
            return "Blu-?Ray.+VC-?1|Blu-?Ray.+AVC|UHD.+blu-?ray.+HEVC|MiniBD"
        if re.match(r"Remux", resource_type, re.IGNORECASE):
            return "Remux"
        if re.match(r"Blu-?Ray", resource_type, re.IGNORECASE):
            return "Blu-?Ray"
        if re.match(r"UHD|UltraHD", resource_type, re.IGNORECASE):
            return "UHD|UltraHD"
        if re.match(r"WEB-?DL|WEB-?RIP", resource_type, re.IGNORECASE):
            return "WEB-?DL|WEB-?RIP"
        if re.match(r"HDTV", resource_type, re.IGNORECASE):
            return "HDTV"
        if re.match(r"[Hx].?265|HEVC", resource_type, re.IGNORECASE):
            return "[Hx].?265|HEVC"
        if re.match(r"[Hx].?264|AVC", resource_type, re.IGNORECASE):
            return "[Hx].?264|AVC"
        return resource_type

    def __parse_effect(self, resource_effect):
        if re.match(r"Dolby[\\s.]+Vision|DOVI|[\\s.]+DV[\\s.]+", resource_effect, re.IGNORECASE):
            return "Dolby[\\s.]+Vision|DOVI|[\\s.]+DV[\\s.]+"
        if re.match(r"Dolby[\\s.]*\\+?Atmos|Atmos", resource_effect, re.IGNORECASE):
            return "Dolby[\\s.]*\\+?Atmos|Atmos"
        if re.match(r"[\\s.]+HDR[\\s.]+|HDR10|HDR10\\+", resource_effect, re.IGNORECASE):
            return "[\\s.]+HDR[\\s.]+|HDR10|HDR10\\+"
        if re.match(r"[\\s.]+SDR[\\s.]+", resource_effect, re.IGNORECASE):
            return "[\\s.]+SDR[\\s.]+"
        return resource_effect

    @staticmethod
    def _get_streaming_platform_from_title(title: str) -> str:
        if not title:
            return ""
        tokens_obj = Tokens(title)
        tokens = tokens_obj.tokens
        if not tokens:
            return ""
        streaming_platforms = StreamingPlatforms()
        for token in tokens:
            if streaming_platforms.is_streaming_platform(token):
                return token
        return ""

    def get_state(self) -> bool:
        return self._enabled or self._category

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

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
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '下载时填充制作组/分辨率等',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'category',
                                            'label': '二级分类自定义填充',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
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
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'clear_handle',
                                            'label': '清理已处理记录',
                                        }
                                    }
                                ]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'update_details',
                                            'label': '填充内容（订阅+下载均生效）',
                                            'items': [
                                                {"title": "资源质量", "value": "资源质量"},
                                                {"title": "分辨率", "value": "分辨率"},
                                                {"title": "特效", "value": "特效"},
                                                {"title": "制作组", "value": "制作组"},
                                                {"title": "站点", "value": "站点"},
                                                {"title": "流媒体平台", "value": "流媒体平台"}
                                            ]
                                        }
                                    }
                                ]
                            },
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
                                            'model': 'update_confs',
                                            'label': '二级分类自定义填充规则',
                                            'rows': 3,
                                            'placeholder': 'category:日番#include:.*(CR.*简繁|简繁英).RLWeb|ADWeb.#sites:观众,红叶PT\n'
                                                           'category:港台剧,日韩剧#include:国粤'
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
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '订阅时填充：流媒体平台（从标题识别）；二级分类规则（按category匹配）。\n'
                                                    '下载时填充：制作组、分辨率、质量、特效等（需开启“下载时填充制作组/分辨率等”开关）。'
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
            "category": False,
            "clear": False,
            "clear_handle": False,
            "update_details": [],
            "update_confs": "",
        }

    def get_page(self) -> List[dict]:
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

        if not isinstance(historys, list):
            historys = [historys]

        historys = sorted(historys, key=lambda x: x.get("time") or 0, reverse=True)

        contens = [
            {
                'component': 'tr',
                'props': {
                    'class': 'text-sm'
                },
                'content': [
                    {
                        'component': 'td',
                        'props': {
                            'class': 'whitespace-nowrap break-keep text-high-emphasis'
                        },
                        'text': history.get("time")
                    },
                    {
                        'component': 'td',
                        'text': history.get("name")
                    },
                    {
                        'component': 'td',
                        'text': history.get("type")
                    },
                    {
                        'component': 'td',
                        'text': history.get("content").encode('utf-8').decode('unicode_escape') if history.get(
                            "content") else ''
                    }
                ]
            } for history in historys
        ]

        return [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 12,
                        },
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {
                                    'hover': True
                                },
                                'content': [
                                    {
                                        'component': 'thead',
                                        'content': [
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '执行时间'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '订阅名称'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '更新类型'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '更新内容'
                                            },
                                        ]
                                    },
                                    {
                                        'component': 'tbody',
                                        'content': contens
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def stop_service(self):
        pass