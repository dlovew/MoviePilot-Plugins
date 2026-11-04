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
from app.chain.subscribe import SubscribeChain
from app.chain.tmdb import TmdbChain
from app.db.oper.site import SiteOper
from app.schemas.types import SystemConfigKey, MediaType, MessageType, MediaSource
from app.sdk.config import settings
from app.sdk.logging import logger
from app.sdk.media import MetaInfo, TorrentInfo
from app.sdk.network import RssHelper
from app.sdk.plugin import _PluginBase
from urllib.parse import urlparse

try:
    from .rss_logic import (
        DEFAULT_PLATFORM_PATTERNS,
        DEFAULT_TIER_RULES,
        choose_best,
        detect_platforms,
        is_due,
        normalized_size,
        now_text,
        parse_json_config,
        pool_key,
        season_matches,
        trim_records,
    )
except ImportError:  # 兼容按顶层模块加载的宿主
    from rss_logic import (  # type: ignore
        DEFAULT_PLATFORM_PATTERNS,
        DEFAULT_TIER_RULES,
        choose_best,
        detect_platforms,
        is_due,
        normalized_size,
        now_text,
        parse_json_config,
        pool_key,
        season_matches,
        trim_records,
    )

lock = Lock()

STATE_KEYS = ("pending", "retry", "history", "handled", "group_choices", "last_run")


class RssSubscribedlovew(_PluginBase):
    """RSS 番剧候选池：先收集各平台资源，窗口到期后按等效单集体积择优订阅一次。"""

    plugin_name = "自定义订阅番剧魔改版 -dlovew"
    plugin_desc = "多 RSS 源收集资源，按窗口比较各平台等效单集体积后择优创建订阅，后续由 MoviePilot 追集。"
    plugin_icon = "rss.png"
    plugin_version = "3.1.0"
    plugin_author = "dlovew"
    author_url = "https://github.com/dlovew"
    plugin_config_prefix = "rssubscribedlovew_"
    plugin_order = 19
    auth_level = 2

    _scheduler: Optional[BackgroundScheduler] = None
    _cache_path: Optional[Path] = None

    # 基础配置
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
    _save_path: str = ""
    _size_range: str = ""

    # 候选池与决策配置
    _collect_window_hours: int = 24
    _platform_patterns: str = ""
    _tier_rules: str = ""
    _auto_detect_episode_group: bool = True
    _auto_select_single_group: bool = False
    _episode_group_overrides: str = ""
    _pending_group_action: str = "notify"
    _retry_unrecognized: bool = True
    _notify_unrecognized: bool = True
    _dry_run: bool = False

    def init_plugin(self, config: dict = None):
        self.stop_service()
        if config:
            self.__validate_and_fix_config(config=config)
            self._enabled = config.get("enabled", False)
            self._cron = config.get("cron", "")
            self._notify = config.get("notify", False)
            self._onlyonce = config.get("onlyonce", False)
            self._address = config.get("address", "")
            self._include = config.get("include", "")
            self._exclude = config.get("exclude", "")
            self._proxy = config.get("proxy", False)
            self._filter = config.get("filter", False)
            self._clear = config.get("clear", False)
            self._save_path = config.get("save_path", "")
            self._size_range = config.get("size_range", "")
            self._collect_window_hours = self.__to_int(config.get("collect_window_hours"), 24)
            self._platform_patterns = config.get("platform_patterns", "") or ""
            self._tier_rules = config.get("tier_rules", "") or ""
            self._auto_detect_episode_group = config.get("auto_detect_episode_group", True)
            self._auto_select_single_group = config.get("auto_select_single_group", False)
            self._episode_group_overrides = config.get("episode_group_overrides", "") or ""
            self._pending_group_action = config.get("pending_group_action", "notify")
            self._retry_unrecognized = config.get("retry_unrecognized", True)
            self._notify_unrecognized = config.get("notify_unrecognized", True)
            self._dry_run = config.get("dry_run", False)

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            logger.info("自定义订阅服务启动，立即运行一次")
            self._scheduler.add_job(
                func=self.check, trigger='date',
                run_date=datetime.datetime.now(tz=pytz.timezone(settings.TZ))
                + datetime.timedelta(seconds=3),
            )
            if self._scheduler.get_jobs():
                self._scheduler.start()

        if self._onlyonce or self._clear:
            self._onlyonce = False
            self._clearflag = bool(self._clear)
            self._clear = False
            self.__update_config()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        prefix = "Bearer 认证由宿主负责；沿用 Vuetify 页面按钮的 GET + params 约定"
        return [
            {
                "path": "/delete_history",
                "endpoint": self.delete_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": f"删除一条决策记录（{prefix}）"
            },
            {
                "path": "/set_episode_group",
                "endpoint": self.set_episode_group,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "为待选剧集组的资源指定剧集组并立即结算"
            },
            {
                "path": "/ignore_group",
                "endpoint": self.ignore_group,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "忽略待选剧集组的资源"
            },
            {
                "path": "/settle",
                "endpoint": self.settle,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "立即结算指定或全部候选（不等窗口）"
            },
            {
                "path": "/run_check",
                "endpoint": self.run_check,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "立即刷新全部 RSS 链接"
            },
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            trigger = CronTrigger.from_crontab(self._cron)
        elif self._enabled:
            trigger = "interval"
        else:
            return []
        service = {
            "id": f"{self.__class__.__name__}.Rss",
            "name": "自定义订阅服务",
            "trigger": trigger,
            "func": self.check,
            "kwargs": {}
        }
        if trigger == "interval":
            service["kwargs"] = {"minutes": 30}
        return [service]

    @staticmethod
    def __to_int(value: Any, default: int) -> int:
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _field(component: str, model: str, label: str, md: int = 4, **props) -> dict:
        """生成设置页中一个 VCol 包裹的表单控件。"""
        return {
            'component': 'VCol',
            'props': {'cols': 12, 'md': md},
            'content': [{
                'component': component,
                'props': {'model': model, 'label': label, **props}
            }]
        }

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        switches = [
            self._field('VSwitch', 'enabled', '启用插件'),
            self._field('VSwitch', 'notify', '发送通知'),
            self._field('VSwitch', 'onlyonce', '立即运行一次'),
            self._field('VSwitch', 'clear', '清空候选池与历史'),
            self._field('VSwitch', 'proxy', '使用代理'),
            self._field('VSwitch', 'filter', '应用订阅过滤规则'),
        ]
        decision_switches = [
            self._field('VSwitch', 'auto_detect_episode_group', '自动探测剧集组'),
            self._field('VSwitch', 'auto_select_single_group', '唯一候选组自动选用'),
            self._field('VSwitch', 'retry_unrecognized', '识别失败进入重试队列'),
            self._field('VSwitch', 'notify_unrecognized', '识别失败发送通知'),
            self._field('VSwitch', 'dry_run', '试运行（只预览不订阅）'),
        ]
        page = [
            {
                'component': 'VForm',
                'content': [
                    {'component': 'VRow', 'content': switches[:3]},
                    {'component': 'VRow', 'content': switches[3:]},
                    {'component': 'VRow', 'content': [
                        self._field('VCronField', 'cron', '执行周期', md=6,
                                    placeholder='5位cron表达式，留空则每30分钟'),
                        self._field('VTextField', 'collect_window_hours', '候选窗口（小时）', md=6,
                                    type='number', placeholder='24'),
                    ]},
                    {'component': 'VRow', 'content': [
                        self._field('VTextarea', 'address', 'RSS 链接（每行一个，全部都会处理）', md=12,
                                    rows=3, placeholder='https://...\nhttps://...'),
                    ]},
                    {'component': 'VRow', 'content': [
                        self._field('VTextarea', 'include', '包含规则（正则，决定哪些资源入池）', md=6,
                                    rows=2, placeholder='(?=.*月新番)(?=.*E01)'),
                        self._field('VTextarea', 'exclude', '排除规则（正则）', md=6,
                                    rows=2),
                    ]},
                    {'component': 'VRow', 'content': [
                        self._field('VTextField', 'size_range', '体积范围（GiB，如 0.5-8）', md=6),
                        self._field('VTextField', 'save_path', '订阅保存目录（留空自动）', md=6),
                    ]},
                    {'component': 'VRow', 'content': decision_switches},
                    {'component': 'VRow', 'content': [
                        self._field('VSelect', 'pending_group_action', '到期未选剧集组', md=6,
                                    items=[
                                        {'title': '通知并继续挂起', 'value': 'notify'},
                                        {'title': '直接忽略', 'value': 'ignore'},
                                    ]),
                        self._field('VTextarea', 'episode_group_overrides',
                                    '剧集组覆盖（探测失败时事后填写，每行 媒体ID=组ID）', md=6,
                                    rows=2, placeholder='12345=5f3a...'),
                    ]},
                    {
                        'component': 'VAlert',
                        'props': {'type': 'info', 'variant': 'tonal', 'class': 'mt-3'},
                        'text': ('入池完全由「包含规则」决定，插件不判断是否季首或合集。'
                                 '识别成功后按「媒体身份 + 季」归并候选，窗口从该季第一条入池资源起算；'
                                 '到期按分层规则比较等效单集体积，只创建一次整季订阅。')
                    },
                    {'component': 'VRow', 'content': [
                        self._field('VTextarea', 'platform_patterns',
                                    '平台识别正则（JSON，留空用默认）', md=6, rows=4,
                                    placeholder='{"VIU": "\\\\bVIU\\\\b"}'),
                        self._field('VTextarea', 'tier_rules',
                                    '分层选优规则（JSON，留空用默认）', md=6, rows=4,
                                    placeholder='[{"tier":1,"platforms":["IQ"],"pick":"smallest_normalized_size"}]'),
                    ]},
                ]
            }
        ]
        model = {
            "enabled": False,
            "notify": False,
            "onlyonce": False,
            "clear": False,
            "proxy": False,
            "filter": False,
            "cron": "*/30 * * * *",
            "collect_window_hours": 24,
            "address": "",
            "include": "",
            "exclude": "",
            "size_range": "",
            "save_path": "",
            "auto_detect_episode_group": True,
            "auto_select_single_group": False,
            "episode_group_overrides": "",
            "pending_group_action": "notify",
            "retry_unrecognized": True,
            "notify_unrecognized": True,
            "dry_run": False,
            "platform_patterns": "",
            "tier_rules": "",
        }
        return page, model

    def _action_button(self, label: str, action: str, params: dict, color: str = 'primary') -> dict:
        return {
            'component': 'VBtn',
            'props': {'color': color, 'variant': 'tonal', 'size': 'small', 'class': 'ma-1'},
            'text': label,
            'events': {
                'click': {
                    'api': f'plugin/{self.__class__.__name__}/{action}',
                    'method': 'get',
                    'params': params,
                }
            }
        }

    def _runtime_page(self) -> List[dict]:
        """数据页：状态摘要 + 待选剧集组 + 等待中 + 已决策 + 待重试。"""
        state = self.__load_state()
        pending = state['pending']
        history = trim_records(state['history'])
        retry = trim_records(state['retry'])
        last = state.get('last_run') or {}
        plugin_id = self.__class__.__name__

        summary = [
            {'component': 'VCardText', 'text': (
                f"最近运行：{last.get('time') or '尚未运行'}　"
                f"入池 {last.get('ingested', 0)} 条　结算 {last.get('settled', 0)} 季　"
                f"窗口 {self._collect_window_hours} 小时　"
                f"{'试运行中（不会订阅）' if self._dry_run else '正常模式'}"
            )},
            {'component': 'VCardText', 'text': (
                f"等待中 {len(pending)} 季　待选剧集组 "
                f"{sum(1 for p in pending.values() if p.get('group_status') == 'mismatch' and not p.get('episode_group'))} 季　"
                f"待重试 {len(retry)} 条　已处理 {len(state['handled'])} 季"
            )},
        ]
        blocks: List[dict] = [{
            'component': 'VCard',
            'props': {'class': 'mb-3'},
            'content': [
                {'component': 'VCardTitle', 'text': '运行状态'},
                *summary,
                {
                    'component': 'VCardActions',
                    'content': [
                        self._action_button('刷新全部 RSS', 'run_check', {}),
                        self._action_button('结算全部候选', 'settle', {}),
                    ]
                },
            ]
        }]

        group_cards = []
        for key, item in pending.items():
            if item.get('group_status') != 'mismatch' or item.get('episode_group'):
                continue
            buttons = []
            for group in item.get('group_candidates') or []:
                buttons.append(self._action_button(
                    f"选用 {group.get('name') or group.get('id')}",
                    'set_episode_group',
                    {'key': key, 'group_id': group.get('id')},
                ))
            buttons.append(self._action_button('忽略', 'ignore_group', {'key': key}, 'grey'))
            group_cards.append({
                'component': 'VCard',
                'props': {'class': 'ma-1'},
                'content': [
                    {'component': 'VCardTitle', 'text': item.get('title') or key},
                    {'component': 'VCardText', 'text': (
                        f"资源侧 S{item.get('season')} 与 TMDB 主季集不匹配；"
                        f"候选组 {len(item.get('group_candidates') or [])} 个。"
                        "选用后立即结算；若未探测到候选组，可在设置页「剧集组覆盖」按 媒体ID=组ID 事后填写。"
                    )},
                    {'component': 'VCardActions', 'content': buttons or [
                        {'component': 'VCardText', 'text': '未探测到候选剧集组，请在设置页「剧集组覆盖」按 媒体ID=组ID 填写后刷新，或忽略'}
                    ]},
                ]
            })
        if group_cards:
            blocks.append({
                'component': 'VCard',
                'props': {'class': 'mb-3'},
                'content': [
                    {'component': 'VCardTitle', 'text': '待选择剧集组'},
                    {'component': 'div', 'props': {'class': 'd-flex flex-wrap'}, 'content': group_cards},
                ]
            })

        waiting = []
        for key, item in pending.items():
            candidates = item.get('candidates') or []
            lines = []
            for candidate in candidates:
                size = candidate.get('normalized_size')
                size_text = f"{size / 1024 ** 3:.2f} GiB/集" if isinstance(size, (int, float)) else '体积未知'
                lines.append(f"{candidate.get('platform') or '未知平台'} · {size_text} · {candidate.get('title') or ''}")
            waiting.append({
                'component': 'VCard',
                'props': {'class': 'ma-1'},
                'content': [
                    {'component': 'VCardTitle', 'text': item.get('title') or key},
                    {'component': 'VCardText', 'text': (
                        f"入池 {item.get('first_seen')}　共 {len(candidates)} 个候选　"
                        f"{'待选剧集组' if item.get('group_status') == 'mismatch' and not item.get('episode_group') else '等待窗口到期'}"
                    )},
                    {'component': 'VCardText', 'text': '；'.join(lines[:8]) or '暂无候选'},
                    {
                        'component': 'VCardActions',
                        'content': [self._action_button('立即结算', 'settle', {'key': key})]
                    },
                ]
            })
        blocks.append({
            'component': 'VCard',
            'props': {'class': 'mb-3'},
            'content': [
                {'component': 'VCardTitle', 'text': '等待中（按等效单集体积择优）'},
                {'component': 'div', 'props': {'class': 'd-flex flex-wrap'},
                 'content': waiting or [{'component': 'VCardText', 'text': '暂无等待中的资源'}]},
            ]
        })

        records = []
        for record in history[:50]:
            records.append({
                'component': 'VCard',
                'props': {'class': 'ma-1'},
                'content': [
                    {'component': 'VCardTitle', 'text': record.get('title') or record.get('key') or '-'},
                    {'component': 'VCardText', 'text': (
                        f"{record.get('action') or '-'}　{record.get('platform') or ''}　"
                        f"{record.get('reason') or record.get('error') or ''}"
                    )},
                    {'component': 'VCardText', 'text': record.get('time') or ''},
                    {
                        'component': 'VCardActions',
                        'content': [self._action_button(
                            '删除记录', 'delete_history', {'key': record.get('id') or ''}, 'error'
                        )]
                    },
                ]
            })
        blocks.append({
            'component': 'VCard',
            'props': {'class': 'mb-3'},
            'content': [
                {'component': 'VCardTitle', 'text': '决策记录'},
                {'component': 'div', 'props': {'class': 'd-flex flex-wrap'},
                 'content': records or [{'component': 'VCardText', 'text': '暂无决策记录'}]},
            ]
        })

        retries = [{
            'component': 'VChip',
            'props': {'class': 'ma-1', 'size': 'small'},
            'text': f"{item.get('title') or '-'}（重试 {item.get('attempts', 0)} 次）"
        } for item in retry[:30]]
        blocks.append({
            'component': 'VCard',
            'props': {'class': 'mb-3'},
            'content': [
                {'component': 'VCardTitle', 'text': '识别失败待重试'},
                {'component': 'div', 'content': retries or [{'component': 'VCardText', 'text': '无'}]},
            ]
        })
        return blocks

    def get_page(self) -> List[dict]:
        try:
            return self._runtime_page()
        except Exception as err:
            logger.error(f"拼装数据页面失败：{str(err)} - {traceback.format_exc()}")
            return [{'component': 'div', 'text': '数据页面加载失败，请查看插件日志'}]

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e))

    # ------------------------------------------------------------------
    # 持久化状态
    # ------------------------------------------------------------------
    def __load_state(self) -> Dict[str, Any]:
        pending = self.get_data('pending') or {}
        if not isinstance(pending, dict):
            pending = {}
        handled = self.get_data('handled') or []
        if not isinstance(handled, list):
            handled = []
        history = self.get_data('history') or []
        if not isinstance(history, list):
            history = []
        retry = self.get_data('retry') or []
        if not isinstance(retry, list):
            retry = []
        choices = self.get_data('group_choices') or {}
        if not isinstance(choices, dict):
            choices = {}
        last_run = self.get_data('last_run') or {}
        if not isinstance(last_run, dict):
            last_run = {}
        return {
            'pending': pending,
            'retry': retry,
            'history': history,
            'handled': handled,
            'group_choices': choices,
            'last_run': last_run,
        }

    def __save_state(self, state: Dict[str, Any]):
        state['history'] = trim_records(state['history'], 200)
        state['retry'] = trim_records(state['retry'], 200)
        state['handled'] = list(dict.fromkeys(state['handled']))[-500:]
        for name in STATE_KEYS:
            self.save_data(name, state[name])

    # ------------------------------------------------------------------
    # 通知
    # ------------------------------------------------------------------
    def __notify(self, title: str, text: str):
        if self._notify:
            self.post_message(mtype=MessageType.Plugin, title=title, text=text)

    def __notify_unrecognized(self, text: str):
        """识别失败通知：独立开关，不再绕过 notify 配置直写 systemmessage。"""
        if self._notify_unrecognized:
            self.post_message(mtype=MessageType.Plugin, title="自定义订阅 · 资源未识别", text=text)

    def __record_retry(self, state: Dict[str, Any], result: dict, rss_url: str, reason: str):
        if not self._retry_unrecognized:
            return
        title = str(result.get('title') or '')
        if any(item.get('title') == title for item in state['retry']):
            return
        state['retry'].append({
            'title': title,
            'description': result.get('description'),
            'size': result.get('size'),
            'enclosure': result.get('enclosure'),
            'link': result.get('link'),
            'pubdate': str(result.get('pubdate') or ''),
            'rss_url': rss_url,
            'reason': reason,
            'attempts': 0,
            'notified': True,
            'time': now_text(),
        })
        self.__notify_unrecognized(f"{title}（{reason}），已加入待重试列表")

    def __retry_unrecognized(self, state: Dict[str, Any]):
        """每个周期重试识别，成功后按正常流程补入候选池。"""
        remaining = []
        for item in state['retry']:
            item['attempts'] = int(item.get('attempts') or 0) + 1
            if item['attempts'] > 30:
                continue
            try:
                meta = MetaInfo(title=item.get('title'), subtitle=item.get('description'))
                mediainfo = self.chain.recognize_media(meta=meta) if meta.name else None
            except Exception as err:
                logger.debug(f"重试识别出错：{str(err)}")
                mediainfo = None
            if not mediainfo:
                remaining.append(item)
                continue
            rebuilt = {
                'title': item.get('title'),
                'description': item.get('description'),
                'enclosure': item.get('enclosure'),
                'link': item.get('link'),
                'size': item.get('size'),
                'pubdate': item.get('pubdate'),
            }
            self.__ingest(state, rebuilt, item.get('rss_url') or '',
                          mediainfo=mediainfo, allow_unknown=True)
        state['retry'] = remaining

    # ------------------------------------------------------------------
    # 入池
    # ------------------------------------------------------------------
    def __platform_patterns(self) -> Dict[str, str]:
        return parse_json_config(self._platform_patterns, DEFAULT_PLATFORM_PATTERNS)

    def __tier_rules(self) -> List[Dict[str, Any]]:
        return parse_json_config(self._tier_rules, DEFAULT_TIER_RULES)

    def __group_overrides(self) -> Dict[str, str]:
        """解析设置页「剧集组覆盖」，键可以是媒体 ID、TMDB ID 或媒体名。"""
        result: Dict[str, str] = {}
        for line in str(self._episode_group_overrides or '').splitlines():
            if '=' not in line or line.strip().startswith('#'):
                continue
            media_key, group_id = line.split('=', 1)
            media_key, group_id = media_key.strip(), group_id.strip()
            if media_key and group_id:
                result[media_key] = group_id
        return result

    def __candidate_episode_groups(self, mediainfo, tmdbid: Any, season: int,
                                   media_id: Any = None) -> List[dict]:
        """自动探测候选剧集组；探测不到时仍给出设置页里事后填写的覆盖项。"""
        raw = getattr(mediainfo, 'episode_groups', None) or []
        groups: List[dict] = []
        if self._auto_detect_episode_group and isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get('id'):
                    groups.append({'id': str(item['id']), 'name': str(item.get('name') or item['id'])})
        if self._auto_detect_episode_group and not groups and tmdbid:
            try:
                fetched = TmdbChain().run_module('tmdb_episode_groups', tmdbid=tmdbid) or []
                if isinstance(fetched, list):
                    for item in fetched:
                        if isinstance(item, dict) and item.get('id'):
                            groups.append({'id': str(item['id']), 'name': str(item.get('name') or item['id'])})
            except Exception as err:
                logger.debug(f"获取剧集组列表失败：{str(err)}")
        verified = []
        for group in groups[:10]:
            try:
                episodes = TmdbChain().tmdb_episodes(tmdbid, season, episode_group=group['id'])
            except Exception as err:
                logger.debug(f"校验剧集组 {group['id']} 失败：{str(err)}")
                continue
            if episodes:
                verified.append({**group, 'season_episodes': len(episodes)})

        # 手动覆盖项无条件列出：用户已明确指定，不必依赖宿主剧集组接口可用
        known = str(media_id or '')
        aliases = {known, str(tmdbid or ''), str(getattr(mediainfo, 'title', '') or '')}
        for media_key, group_id in self.__group_overrides().items():
            if media_key not in aliases:
                continue
            if any(group['id'] == group_id for group in verified):
                continue
            verified.append({'id': group_id, 'name': f'手动覆盖 {group_id}', 'season_episodes': 0})
        return verified

    def __ingest(self, state: Dict[str, Any], result: dict, rss_url: str,
                 mediainfo=None, allow_unknown: bool = False):
        """处理单条 RSS 资源：过滤 → 识别 → 归键 → 入池。

        ``allow_unknown`` 仅用于重试队列：TMDB 季集信息仍缺失时按主季订阅，
        避免新番因元数据不全被永久挂起。
        """
        title = str(result.get('title') or '')
        description = str(result.get('description') or '')
        combined = f"{title} {description}"
        if not title:
            return
        if self._include and not re.search(r'%s' % self._include, combined, re.IGNORECASE):
            return
        if self._exclude and re.search(r'%s' % self._exclude, combined, re.IGNORECASE):
            return
        if self._size_range:
            size_value = result.get('size')
            if not size_value:
                return
            try:
                bounds = [float(part) * 1024 ** 3 for part in str(self._size_range).split('-')]
                if len(bounds) == 1 and float(size_value) < bounds[0]:
                    return
                if len(bounds) > 1 and not bounds[0] <= float(size_value) <= bounds[1]:
                    return
            except (TypeError, ValueError):
                return

        if mediainfo is None:
            meta = MetaInfo(title=title, subtitle=description)
            if not meta.name:
                self.__record_retry(state, result, rss_url, '标题无法解析')
                return
            mediainfo = self.chain.recognize_media(meta=meta)
            if not mediainfo:
                self.__record_retry(state, result, rss_url, 'TMDB 未识别到媒体')
                return
        else:
            meta = MetaInfo(title=title, subtitle=description)

        if self._filter:
            try:
                filter_groups = self.systemconfig.get(SystemConfigKey.SubscribeFilterRuleGroups)
                torrentinfo = TorrentInfo(
                    title=title,
                    description=description,
                    enclosure=result.get('enclosure'),
                    page_url=result.get('link'),
                    size=result.get('size'),
                    pubdate=str(result.get('pubdate') or ''),
                    site_proxy=self._proxy,
                )
                if not self.chain.filter_torrents(rule_groups=filter_groups,
                                                  torrent_list=[torrentinfo],
                                                  mediainfo=mediainfo):
                    return
            except Exception as err:
                logger.debug(f"过滤规则执行失败，忽略该条：{str(err)}")

        season_raw = getattr(meta, 'begin_season', None) or getattr(meta, 'season', None)
        try:
            season = int(re.search(r'(\d+)', str(season_raw)).group(1)) if season_raw else 1
        except (TypeError, ValueError, AttributeError):
            season = 1
        episodes = list(getattr(meta, 'episode_list', None) or [])
        try:
            episode_count = max(len(episodes), 1)
        except TypeError:
            episode_count = 1

        media_source = getattr(mediainfo, 'media_source', None)
        media_source_value = getattr(media_source, 'value', None) or str(media_source or 'tmdb')
        media_id = str(getattr(mediainfo, 'media_id', None) or getattr(mediainfo, 'tmdb_id', None) or '')
        if not media_id:
            self.__record_retry(state, result, rss_url, '媒体身份缺失')
            return

        group_choice = state['group_choices'].get(media_id)
        key = pool_key(media_source_value, media_id, season, group_choice)
        if key in state['handled']:
            return

        platforms = detect_platforms(title, self.__platform_patterns())
        platform = platforms[0] if platforms else 'UNKNOWN'
        status = season_matches(getattr(mediainfo, 'seasons', None), season, episodes)
        if status == 'unknown' and not allow_unknown:
            self.__record_retry(state, result, rss_url, 'TMDB 季集信息暂缺')
            return
        tmdbid = getattr(mediainfo, 'tmdb_id', None) or media_id

        item = state['pending'].get(key)
        if not item:
            item = {
                'key': key,
                'media_source': media_source_value,
                'media_id': media_id,
                'tmdbid': str(tmdbid),
                'season': season,
                'title': getattr(mediainfo, 'title_year', None) or getattr(mediainfo, 'title', None) or title,
                'year': getattr(mediainfo, 'year', None),
                'poster': self.__safe_poster(mediainfo),
                'mtype': getattr(getattr(mediainfo, 'type', None), 'value', None),
                'group_status': status,
                'episode_group': group_choice,
                'group_candidates': [],
                'group_notified': False,
                'group_ignored': False,
                'first_seen': now_text(),
                'last_seen': now_text(),
                'candidates': [],
            }
            if status == 'mismatch':
                item['group_candidates'] = self.__candidate_episode_groups(
                    mediainfo, tmdbid, season, media_id
                )
                if len(item['group_candidates']) == 1 and self._auto_select_single_group:
                    item['episode_group'] = item['group_candidates'][0]['id']
            state['pending'][key] = item
        else:
            item['last_seen'] = now_text()
            if item.get('group_status') == 'unknown' and status != 'unknown':
                item['group_status'] = status

        if any(c.get('title') == title and c.get('rss_url') == rss_url
               for c in item['candidates']):
            return
        item['candidates'].append({
            'title': title,
            'platform': platform,
            'team': getattr(meta, 'resource_team', None),
            'resolution': getattr(meta, 'resource_pix', None),
            'quality': getattr(meta, 'resource_type', None),
            'effect': getattr(meta, 'resource_effect', None),
            'size': result.get('size'),
            'episode_count': episode_count,
            'normalized_size': normalized_size(result.get('size'), episode_count),
            'rss_url': rss_url,
            'enclosure': result.get('enclosure'),
            'pubdate': str(result.get('pubdate') or ''),
        })
        state['last_run']['ingested'] = int(state['last_run'].get('ingested') or 0) + 1

    # ------------------------------------------------------------------
    # 结算
    # ------------------------------------------------------------------
    def __settle_due(self, state: Dict[str, Any], force: bool = False):
        for key in list(state['pending'].keys()):
            item = state['pending'][key]
            if not force and not is_due(item.get('first_seen'), self._collect_window_hours):
                continue
            self.__settle_key(state, key)

    def __settle_key(self, state: Dict[str, Any], key: str):
        item = state['pending'].get(key)
        if not item:
            return
        if item.get('group_ignored'):
            self.__finalize(state, key, item, 'ignored', reason='已忽略剧集组资源')
            return
        if item.get('group_status') == 'mismatch' and not item.get('episode_group'):
            if self._pending_group_action == 'ignore':
                self.__finalize(state, key, item, 'ignored', reason='到期未选剧集组，按配置忽略')
            elif not item.get('group_notified'):
                item['group_notified'] = True
                self.__notify('自定义订阅 · 待选剧集组',
                              f"{item.get('title')} 的 S{item.get('season')} 与 TMDB 主季集不匹配，"
                              "请在插件数据页选择剧集组后订阅")
            return

        winner, reason = choose_best(item.get('candidates') or [], self.__tier_rules())
        if not winner:
            self.__finalize(state, key, item, 'no_candidate', reason=reason)
            return
        if self._dry_run:
            if not item.get('dry_run_done'):
                item['dry_run_done'] = True
                self.__record(state, item, 'dry_run', reason=f"试运行：{reason}",
                              platform=winner.get('platform'))
            return

        subscribe_id, error, detail = self.__create_subscription(item, winner)
        if error:
            self.__finalize(state, key, item, 'failed', reason=detail or error,
                            platform=winner.get('platform'))
            self.__notify('自定义订阅 · 订阅失败', f"{item.get('title')}：{detail or error}")
            return
        self.__finalize(state, key, item, 'subscribed', reason=reason,
                        platform=winner.get('platform'), subscribe_id=subscribe_id)
        state['last_run']['settled'] = int(state['last_run'].get('settled') or 0) + 1

    def __record(self, state: Dict[str, Any], item: dict, action: str, reason: str = '',
                 platform: str = '', subscribe_id: Any = None, error: str = ''):
        state['history'].append({
            'id': f"{item.get('key')}#{now_text()}",
            'key': item.get('key'),
            'title': item.get('title'),
            'action': action,
            'platform': platform,
            'reason': reason,
            'subscribe_id': str(subscribe_id) if subscribe_id else '',
            'error': error,
            'poster': item.get('poster'),
            'time': now_text(),
        })

    def __finalize(self, state: Dict[str, Any], key: str, item: dict, action: str,
                   reason: str = '', platform: str = '', subscribe_id: Any = None,
                   error: str = ''):
        self.__record(state, item, action, reason, platform, subscribe_id, error)
        if action in ('subscribed', 'ignored', 'no_candidate') and key not in state['handled']:
            state['handled'].append(key)
        state['pending'].pop(key, None)

    def __create_subscription(self, item: dict, winner: dict) -> Tuple[Any, str, str]:
        """创建一次整季订阅并校验返回值；失败原因回传用于通知与决策记录。"""
        try:
            try:
                source = MediaSource(item.get('media_source'))
            except (TypeError, ValueError):
                source = MediaSource.TMDB
            kwargs = {
                'include': self.__build_include(winner.get('platform'), winner.get('team')),
                'sites': self.__get_site_ids(winner.get('rss_url') or '') or None,
                'username': 'RSS订阅',
                'exist_ok': True,
                'media_source': source,
                'media_id': item.get('media_id'),
                'season': item.get('season'),
            }
            if item.get('episode_group'):
                kwargs['episode_group'] = item['episode_group']
            if self._save_path:
                kwargs['save_path'] = self._save_path
            resolution = self.__parse_pix(winner.get('resolution'))
            quality = self.__parse_type(winner.get('quality'))
            effect = self.__parse_effect(winner.get('effect'))
            for name, value in (('resolution', resolution), ('quality', quality), ('effect', effect)):
                if value:
                    kwargs[name] = value
            subscribe_id, error = SubscribeChain().add(
                title=item.get('title'),
                year=item.get('year'),
                mtype=MediaType.TV,
                **kwargs
            )
            if error or not subscribe_id:
                return None, 'subscribe_failed', str(error or '宿主未返回订阅 ID')
            logger.info(f"添加订阅成功：{item.get('title')} S{item.get('season')} "
                        f"平台={winner.get('platform')} include={kwargs['include']} "
                        f"剧集组={item.get('episode_group') or '无'}")
            return subscribe_id, '', ''
        except Exception as err:
            logger.error(f"添加订阅异常：{str(err)} - {traceback.format_exc()}")
            return None, 'exception', str(err)

    def check(self):
        """刷新全部 RSS → 入池 → 结算到期候选 → 持久化。单个源失败不影响其它源。"""
        if not self._address:
            return
        state = self.__load_state()
        if self._clearflag:
            for key in STATE_KEYS:
                state[key] = {} if key in ('pending', 'group_choices', 'last_run') else []
            self._clearflag = False
        state['last_run']['time'] = now_text()
        state['last_run']['ingested'] = 0
        state['last_run']['settled'] = 0

        if self._retry_unrecognized:
            try:
                self.__retry_unrecognized(state)
            except Exception as err:
                logger.error(f"重试识别队列失败：{str(err)}")

        sources = [url.strip() for url in str(self._address).split('\n') if url.strip()]
        for url in sources:
            try:
                results = RssHelper().parse(url, proxy=self._proxy)
            except Exception as err:
                logger.error(f"RSS 解析失败，继续处理其它链接：{url} - {str(err)}")
                continue
            if not results:
                logger.warning(f"未获取到 RSS 数据，继续处理其它链接：{url}")
                continue
            ingested = 0
            for result in results:
                try:
                    self.__ingest(state, dict(result), url)
                    ingested += 1
                except Exception as err:
                    logger.error(f"处理 RSS 条目出错：{str(err)} - {traceback.format_exc()}")
            logger.info(f"RSS {url} 刷新完成，处理 {ingested} 条")

        try:
            self.__settle_due(state)
        except Exception as err:
            logger.error(f"结算候选池失败：{str(err)} - {traceback.format_exc()}")
        self.__save_state(state)

    # ------------------------------------------------------------------
    # 数据页 / 按钮 API
    # ------------------------------------------------------------------
    def delete_history(self, key: str):
        history = self.get_data('history') or []
        if not isinstance(history, list):
            history = []
        remained = [item for item in history if item.get('id') != key]
        self.save_data('history', remained)
        return schemas.Response(success=True, message="删除成功")

    def set_episode_group(self, key: str, group_id: str = ""):
        state = self.__load_state()
        item = state['pending'].get(key)
        if not item:
            return schemas.Response(success=False, message="未找到待处理资源")
        group_id = str(group_id or '').strip()
        if not group_id:
            return schemas.Response(success=False, message="剧集组 ID 不能为空")
        item['episode_group'] = group_id
        item['group_notified'] = False
        state['group_choices'][str(item.get('media_id'))] = group_id
        new_key = pool_key(item.get('media_source'), item.get('media_id'),
                           item.get('season'), group_id)
        if new_key != key:
            state['pending'].pop(key, None)
            item['key'] = new_key
            state['pending'][new_key] = item
            key = new_key
        self.__settle_key(state, key)
        self.__save_state(state)
        return schemas.Response(success=True, message="已选用剧集组并结算")

    def ignore_group(self, key: str):
        state = self.__load_state()
        item = state['pending'].get(key)
        if not item:
            return schemas.Response(success=False, message="未找到待处理资源")
        item['group_ignored'] = True
        self.__finalize(state, key, item, 'ignored', reason='手动忽略剧集组资源')
        self.__save_state(state)
        return schemas.Response(success=True, message="已忽略")

    def settle(self, key: str = ""):
        state = self.__load_state()
        if key:
            self.__settle_key(state, key)
        else:
            self.__settle_due(state, force=True)
        self.__save_state(state)
        return schemas.Response(success=True, message="结算完成")

    def run_check(self):
        try:
            self.check()
            return schemas.Response(success=True, message="RSS 刷新完成")
        except Exception as err:
            logger.error(f"手动刷新失败：{str(err)}")
            return schemas.Response(success=False, message=str(err))

    def __update_config(self):
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
            "save_path": self._save_path,
            "size_range": self._size_range,
            "collect_window_hours": self._collect_window_hours,
            "platform_patterns": self._platform_patterns,
            "tier_rules": self._tier_rules,
            "auto_detect_episode_group": self._auto_detect_episode_group,
            "auto_select_single_group": self._auto_select_single_group,
            "episode_group_overrides": self._episode_group_overrides,
            "pending_group_action": self._pending_group_action,
            "retry_unrecognized": self._retry_unrecognized,
            "notify_unrecognized": self._notify_unrecognized,
            "dry_run": self._dry_run,
        })

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def __build_include(platform: str, team: str = None) -> str:
        """平台未识别时不加平台条件，避免生成永远搜不到的 include 正则。"""
        parts = []
        if platform and platform != 'UNKNOWN':
            parts.append(f"(?=.*{platform})")
        if team:
            parts.append(f"(?=.*{team})")
        return "".join(parts)

    @staticmethod
    def __safe_poster(mediainfo) -> str:
        try:
            getter = getattr(mediainfo, 'get_poster_image', None)
            return str(getter() or '') if callable(getter) else ''
        except Exception:
            return ''

    @staticmethod
    def __season_label(meta) -> str:
        season = getattr(meta, 'begin_season', None) or getattr(meta, 'season', None)
        if not season:
            return ""
        if isinstance(season, str):
            matched = re.search(r"(\d+)", season)
            season = int(matched.group(1)) if matched else None
        if season is None:
            return ""
        try:
            return f"S{int(season):02d}"
        except (TypeError, ValueError):
            return f"S{season}"

    @staticmethod
    def __parse_pix(pix) -> Optional[str]:
        if not pix:
            return None
        pix = str(pix).lower()
        if "2160" in pix or "4k" in pix:
            return "4K|2160p|x2160"
        if "1080" in pix:
            return "1080[pi]|x1080"
        if "720" in pix:
            return "720[pi]|x720"
        return str(pix)

    @staticmethod
    def __parse_type(type_) -> Optional[str]:
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

    @staticmethod
    def __is_number_or_range(value):
        return bool(re.match(r"^\d+(\.\d+)?(-\d+(\.\d+)?)?$", value))

    def __validate_and_fix_config(self, config: dict = None) -> bool:
        size_range = (config or {}).get("size_range")
        if size_range and not self.__is_number_or_range(str(size_range)):
            self.__notify('自定义订阅', f"种子大小设置错误：{size_range}")
            config["size_range"] = ""
            return False
        return True

    def __get_site_ids(self, rss_url: str) -> List[int]:
        """按 RSS 域名匹配站点；匹配不到时返回空，由宿主回退默认站点配置。"""
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
            domain = str(getattr(site, 'domain', None) or '').lower().lstrip('.')
            if not domain:
                continue
            # 后缀边界匹配，避免 example.com 误命中 notexample.com
            if netloc == domain or netloc.endswith('.' + domain):
                ids.append(site.id)
        return ids
