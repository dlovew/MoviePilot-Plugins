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
from app.chain.media import MediaChain
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
        DEFAULT_PLATFORM_TOKENS,
        DEFAULT_TIER1_PLATFORMS,
        DEFAULT_TIER2_PLATFORMS,
        DEFAULT_TIER3_PLATFORMS,
        build_include,
        build_tier_rules,
        candidate_platform_items,
        choose_best,
        detect_platforms,
        elapsed_text,
        group_type_label,
        is_due,
        normalized_size,
        now_text,
        pool_key,
        reidentify_platforms,
        season_matches,
        summarize_seasons,
        trim_records,
    )
except ImportError:  # 兼容按顶层模块加载的宿主
    from rss_logic import (  # type: ignore
        DEFAULT_PLATFORM_TOKENS,
        DEFAULT_TIER1_PLATFORMS,
        DEFAULT_TIER2_PLATFORMS,
        DEFAULT_TIER3_PLATFORMS,
        build_include,
        build_tier_rules,
        candidate_platform_items,
        choose_best,
        detect_platforms,
        elapsed_text,
        group_type_label,
        is_due,
        normalized_size,
        now_text,
        pool_key,
        reidentify_platforms,
        season_matches,
        summarize_seasons,
        trim_records,
    )

lock = Lock()

STATE_KEYS = ("pending", "retry", "history", "handled", "group_choices", "last_run")


class RssSubscribedlovew(_PluginBase):
    """RSS 番剧候选池：先收集各平台资源，窗口到期后按等效单集体积择优订阅一次。"""

    plugin_name = "自定义订阅番剧魔改版 -dlovew"
    plugin_desc = "多 RSS 源收集资源，按窗口比较各平台等效单集体积后择优创建订阅，后续由 MoviePilot 追集。"
    plugin_icon = "rss.png"
    plugin_version = "3.1.6"
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
    _tier1_platforms: List[str] = DEFAULT_TIER1_PLATFORMS
    _tier2_platforms: List[str] = DEFAULT_TIER2_PLATFORMS
    _tier3_platforms: List[str] = DEFAULT_TIER3_PLATFORMS
    _tier2_unconditional: bool = True
    _custom_platforms: str = ""
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
            self._tier1_platforms = self.__as_list(config.get("tier1_platforms"), DEFAULT_TIER1_PLATFORMS)
            self._tier2_platforms = self.__as_list(config.get("tier2_platforms"), DEFAULT_TIER2_PLATFORMS)
            self._tier3_platforms = self.__as_list(config.get("tier3_platforms"), DEFAULT_TIER3_PLATFORMS)
            self._tier2_unconditional = bool(config.get("tier2_unconditional", True))
            self._custom_platforms = config.get("custom_platforms", "") or ""
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
    def __as_list(value: Any, default: List[str]) -> List[str]:
        """兼容 VSelect multiple 的数组与配置迁移时的逗号分隔字符串。"""
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [part.strip() for part in value.split(',') if part.strip()]
        return list(default)

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
                        self._field('VSelect', 'tier1_platforms',
                                    'Tier1 首选平台（按等效单集体积选最小）', md=4,
                                    multiple=True, chips=True, clearable=True,
                                    items=self.__platform_items()),
                        self._field('VSelect', 'tier2_platforms', 'Tier2 兜底平台', md=4,
                                    multiple=True, chips=True, clearable=True,
                                    items=self.__platform_items()),
                        self._field('VSelect', 'tier3_platforms', 'Tier3 其余兜底平台', md=4,
                                    multiple=True, chips=True, clearable=True,
                                    items=self.__platform_items()),
                    ]},
                    {'component': 'VRow', 'content': [
                        self._field('VSwitch', 'tier2_unconditional',
                                    'Tier2 无条件优先（不与 Tier3 比体积）', md=6),
                        self._field('VTextarea', 'custom_platforms',
                                    '自定义平台缩写（每行一个，按资源标题里的写法）', md=6,
                                    rows=2, placeholder='ABEMA'),
                    ]},
                    {
                        'component': 'VAlert',
                        'props': {'type': 'info', 'variant': 'tonal', 'class': 'mb-3'},
                        'text': ('平台缩写直接取自资源标题原文，订阅 include 使用同一片段，'
                                 '例如标题写 CR 就不会写成 Crunchyroll、写 MyVideo 不会写成 MYVIDEO。'
                                 '新增平台先在自定义框填缩写并保存，即可在上方下拉中勾选。')
                    },
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
            "tier1_platforms": list(DEFAULT_TIER1_PLATFORMS),
            "tier2_platforms": list(DEFAULT_TIER2_PLATFORMS),
            "tier3_platforms": list(DEFAULT_TIER3_PLATFORMS),
            "tier2_unconditional": True,
            "custom_platforms": "",
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

    def _group_option_card(self, key: str, group: dict) -> dict:
        """候选剧集组选项卡片：每项自带静态 group_id，点击即选用并结算。

        V3 数据页的 PageRender 不支持 v-model，真正回传选中值的 VSelect 无法提交，
        因此复刻主程序按剧集组订阅时的「可点击选项」形态。
        """
        meta_parts = [str(group.get('type_label') or '未知类型')]
        if group.get('group_count'):
            meta_parts.append(f"{group['group_count']} 季")
        if group.get('episode_count'):
            meta_parts.append(f"{group['episode_count']} 集")
        if group.get('season_episodes'):
            meta_parts.append(f"该季 {group['season_episodes']} 集")
        return {
            'component': 'VCard',
            'props': {
                'class': 'ma-1 pa-2',
                'color': 'primary',
                'variant': 'tonal',
                'style': 'cursor:pointer;min-width:13rem;max-width:19rem',
            },
            'events': {
                'click': {
                    'api': f'plugin/{self.__class__.__name__}/set_episode_group',
                    'method': 'get',
                    'params': {'key': key, 'group_id': group.get('id')},
                }
            },
            'content': [
                {'component': 'VCardTitle', 'props': {'class': 'text-body-1'},
                 'text': str(group.get('name') or group.get('id') or '-')},
                {'component': 'VCardText', 'props': {'class': 'pa-0 px-2 text-caption'},
                 'text': f"{' · '.join(meta_parts)}　ID {group.get('id') or '-'}"},
            ],
        }

    @staticmethod
    def _section(title: str, rows: List[dict], empty_text: str = '无') -> dict:
        """全宽单列区块，避免 flex-wrap 导致一行里卡片数量忽多忽少。"""
        return {
            'component': 'VCard',
            'props': {'class': 'mb-3 pa-2', 'variant': 'text'},
            'content': [
                {'component': 'VCardTitle',
                 'props': {'class': 'text-subtitle-2 text-medium-emphasis'},
                 'text': title},
                {'component': 'div', 'props': {
                    'style': 'display:flex;flex-direction:column;gap:0.5rem'},
                 'content': rows or [
                     {'component': 'VCardText', 'props': {'class': 'text-caption'},
                      'text': empty_text}
                 ]},
            ]
        }

    @staticmethod
    def _header_row(title_node: dict, actions: List[dict]) -> dict:
        """标题与操作按钮左右对齐的一行。"""
        return {
            'component': 'div',
            'props': {'style': ('display:flex;justify-content:space-between;'
                                'align-items:center;gap:0.75rem;flex-wrap:wrap')},
            'content': [title_node, {'component': 'div', 'content': actions}],
        }

    @staticmethod
    def _text_line(text: str, css: str = 'text-caption text-medium-emphasis') -> dict:
        return {'component': 'div', 'props': {'class': css}, 'text': text}

    @staticmethod
    def _tmdb_title(title: str, tmdbid: Any) -> dict:
        """标题链接到 TMDB 剧集页，并附一个季集/剧集组入口，便于人工辨别。"""
        try:
            tv_id = int(str(tmdbid or '').strip())
        except (TypeError, ValueError):
            tv_id = 0
        if not tv_id:
            return {'component': 'div',
                    'props': {'class': 'text-subtitle-1 font-weight-medium'},
                    'text': title}
        base = f'https://www.themoviedb.org/tv/{tv_id}'
        return {
            'component': 'div',
            'props': {'style': 'display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap'},
            'content': [
                {'component': 'a',
                 'props': {'href': base, 'target': '_blank', 'rel': 'noopener noreferrer',
                           'class': ('text-subtitle-1 font-weight-medium text-primary '
                                     'text-decoration-none')},
                 'text': f'{title} ↗'},
                {'component': 'a',
                 'props': {'href': f'{base}/episodes?active_nav_item=episode_groups',
                           'target': '_blank', 'rel': 'noopener noreferrer',
                           'class': 'text-caption text-primary text-decoration-none'},
                 'text': '季集 / 剧集组 ↗'},
            ],
        }

    @staticmethod
    def _platform_chips(candidates: List[dict]) -> List[dict]:
        """候选平台标签带等效体积；未识别平台警示显示并列出可复制的原始标题。"""
        items = candidate_platform_items(candidates)
        if not items:
            return [{'component': 'div', 'props': {'class': 'text-caption'},
                     'text': '暂无候选'}]
        chips = []
        unknown_titles = []
        for item in items:
            unknown = bool(item.get('unknown'))
            text = f"{item['label']} · {item.get('size_text') or '体积未知'}"
            chips.append({
                'component': 'VChip',
                'props': {
                    'size': 'small',
                    'class': 'ma-1',
                    'color': 'warning' if unknown else 'primary',
                    'variant': 'flat' if unknown else 'tonal',
                },
                'text': f"⚠ {text}" if unknown else text,
            })
            if unknown and item.get('title'):
                unknown_titles.append(item['title'])

        blocks = [{'component': 'div', 'props': {'class': 'd-flex flex-wrap'},
                   'content': chips}]
        if unknown_titles:
            blocks.append({
                'component': 'div',
                'props': {'class': 'text-caption text-medium-emphasis mt-1'},
                'content': [
                    {'component': 'div',
                     'text': '未识别平台：复制下方标题里的缩写，填入设置页「自定义平台缩写」'},
                    *[{'component': 'div',
                       'props': {'style': ('user-select:all;word-break:break-all;'
                                           'margin-top:0.25rem')},
                       'text': title} for title in unknown_titles[:3]],
                ],
            })
        return blocks

    def _runtime_page(self) -> List[dict]:
        """数据页：全宽单列布局，状态摘要 + 待选剧集组 + 等待中 + 决策记录 + 待重试。"""
        state = self.__load_state()
        pending = state['pending']
        history = trim_records(state['history'])
        retry = trim_records(state['retry'])
        last = state.get('last_run') or {}

        group_pending = sum(1 for item in pending.values()
                            if item.get('group_status') == 'mismatch'
                            and not item.get('episode_group'))
        reidentified = int(last.get('reidentified') or 0)
        reidentified_text = f"　重识别 {reidentified}" if reidentified else ''
        blocks: List[dict] = [{
            'component': 'VCard',
            'props': {'class': 'mb-3 pa-2', 'variant': 'tonal'},
            'content': [
                self._text_line(
                    f"最近运行 {last.get('time') or '尚未运行'}　"
                    f"入池 {last.get('ingested', 0)}　结算 {last.get('settled', 0)}　"
                    f"窗口 {self._collect_window_hours}h　"
                    f"{'试运行' if self._dry_run else '正常'}"
                ),
                self._text_line(
                    f"等待中 {len(pending)}　待选剧集组 {group_pending}　"
                    f"待重试 {len(retry)}　已处理 {len(state['handled'])}"
                    f"{reidentified_text}"
                ),
                {'component': 'VCardActions', 'content': [
                    self._action_button('刷新全部 RSS', 'run_check', {}),
                    self._action_button('结算全部候选', 'settle', {}),
                ]},
            ]
        }]

        group_rows = []
        for key, item in pending.items():
            if item.get('group_status') != 'mismatch' or item.get('episode_group'):
                continue
            groups = item.get('group_candidates') or []
            group_rows.append({
                'component': 'VCard',
                'props': {'class': 'mb-2 pa-3', 'variant': 'outlined', 'color': 'warning'},
                'content': [
                    self._header_row(
                        self._tmdb_title(str(item.get('title') or key), item.get('tmdbid')),
                        [self._action_button('忽略', 'ignore_group', {'key': key}, 'grey')],
                    ),
                    self._text_line(
                        f"{item.get('resource_season_text') or '-'} → "
                        f"TMDB {item.get('main_seasons_text') or '-'}　"
                        f"已挂起 {elapsed_text(item.get('first_seen'))}"
                    ),
                    {'component': 'div', 'props': {'class': 'd-flex flex-wrap mt-2'},
                     'content': [self._group_option_card(key, group) for group in groups[:8]] or [
                         self._text_line('无候选组，可在设置页填「剧集组覆盖」或忽略')
                     ]},
                ]
            })
        if group_rows:
            blocks.append(self._section(
                f'待选择剧集组（{len(group_rows)}）· 点击卡片选用', group_rows
            ))

        waiting = []
        for key, item in pending.items():
            candidates = item.get('candidates') or []
            status_text = ('待选剧集组' if item.get('group_status') == 'mismatch'
                           and not item.get('episode_group') else '等待窗口到期')
            waiting.append({
                'component': 'VCard',
                'props': {'class': 'mb-2 pa-3', 'variant': 'tonal'},
                'content': [
                    self._header_row(
                        {'component': 'div',
                         'props': {'class': 'text-subtitle-1 font-weight-medium'},
                         'text': str(item.get('title') or key)},
                        [self._action_button('立即结算', 'settle', {'key': key})],
                    ),
                    self._text_line(
                        f"入池 {item.get('first_seen') or '-'}　"
                        f"共 {len(candidates)} 个候选　{status_text}"
                    ),
                    *self._platform_chips(candidates),
                ]
            })
        blocks.append(self._section('等待中', waiting, '暂无等待中的资源'))

        records = []
        for record in history[:30]:
            records.append({
                'component': 'VCard',
                'props': {'class': 'mb-2 pa-3', 'variant': 'tonal'},
                'content': [
                    self._header_row(
                        {'component': 'div',
                         'props': {'class': 'text-subtitle-1 font-weight-medium'},
                         'text': str(record.get('title') or record.get('key') or '-')},
                        [self._action_button('删除', 'delete_history',
                                            {'key': record.get('id') or ''}, 'error')],
                    ),
                    self._text_line(
                        f"{record.get('time') or '-'}　{record.get('action') or '-'}　"
                        f"{record.get('platform') or ''}　"
                        f"{record.get('reason') or record.get('error') or ''}"
                    ),
                ]
            })
        blocks.append(self._section('决策记录', records, '暂无决策记录'))

        retries = [{
            'component': 'VChip',
            'props': {'class': 'ma-1', 'size': 'small', 'variant': 'tonal'},
            'text': f"{item.get('title') or '-'}（重试 {item.get('attempts', 0)} 次）"
        } for item in retry[:30]]
        blocks.append(self._section(
            '识别失败待重试',
            [{'component': 'div', 'props': {'class': 'd-flex flex-wrap'},
              'content': retries}] if retries else [],
            '无',
        ))
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
    def __platform_tokens(self) -> List[str]:
        """默认词表 + 自定义缩写 + 已勾选值，识别与下拉选项共用。"""
        tokens = list(DEFAULT_PLATFORM_TOKENS)
        for line in str(self._custom_platforms or '').splitlines():
            token = line.strip()
            if token and not token.startswith('#') and token not in tokens:
                tokens.append(token)
        for selected in (self._tier1_platforms, self._tier2_platforms, self._tier3_platforms):
            for token in selected or []:
                if token and token not in tokens:
                    tokens.append(token)
        return tokens

    def __platform_items(self) -> List[dict]:
        return [{'title': token, 'value': token} for token in self.__platform_tokens()]

    def __tier_rules(self) -> List[Dict[str, Any]]:
        return build_tier_rules(
            self._tier1_platforms,
            self._tier2_platforms,
            self._tier3_platforms,
            self._tier2_unconditional,
        )

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

    @staticmethod
    def __group_record(raw: Any) -> Optional[dict]:
        """把 dict 或 MediaEpisodeGroup 对象统一成可展示的候选组记录。"""
        def pick(name: str) -> Any:
            if isinstance(raw, dict):
                return raw.get(name)
            return getattr(raw, name, None)

        group_id = pick('id')
        if group_id is None or str(group_id) == '':
            return None

        def number(name: str) -> int:
            try:
                return int(pick(name) or 0)
            except (TypeError, ValueError):
                return 0

        return {
            'id': str(group_id),
            'name': str(pick('name') or group_id),
            'type_label': group_type_label(pick('type')),
            'group_count': number('group_count'),
            'episode_count': number('episode_count'),
            'description': str(pick('description') or ''),
        }

    def __candidate_episode_groups(self, mediainfo, tmdbid: Any, season: int,
                                   media_id: Any = None) -> List[dict]:
        """自动探测候选剧集组，带组名/类型/季数/集数；探测不到时仍列出手动覆盖项。"""
        raw_groups: List[Any] = []
        if self._auto_detect_episode_group:
            source = getattr(mediainfo, 'episode_groups', None) or []
            if isinstance(source, (list, tuple)):
                raw_groups = list(source)
            if not raw_groups and tmdbid:
                # 与宿主 media/groups/{tmdbid} 一致：按明确身份重新识别取剧集组
                try:
                    refreshed = MediaChain().recognize_media(
                        media_source=MediaSource.TMDB,
                        media_id=str(tmdbid),
                        mtype=MediaType.TV,
                    )
                    fetched = getattr(refreshed, 'episode_groups', None) or []
                    if isinstance(fetched, (list, tuple)):
                        raw_groups = list(fetched)
                except Exception as err:
                    logger.debug(f"获取剧集组列表失败：{str(err)}")

        verified: List[dict] = []
        for raw in raw_groups[:12]:
            record = self.__group_record(raw)
            if not record:
                continue
            try:
                episodes = TmdbChain().tmdb_episodes(
                    tmdbid, season, episode_group=record['id']
                )
            except Exception as err:
                logger.debug(f"校验剧集组 {record['id']} 失败：{str(err)}")
                episodes = None
            # 接口确认该组没有此季时跳过；接口不可用时仍保留，交用户判断
            if episodes is not None and not episodes:
                continue
            record['season_episodes'] = len(episodes or [])
            verified.append(record)

        # 手动覆盖项无条件列出：用户已明确指定，不必依赖宿主剧集组接口可用
        known = str(media_id or '')
        aliases = {known, str(tmdbid or ''), str(getattr(mediainfo, 'title', '') or '')}
        for media_key, group_id in self.__group_overrides().items():
            if media_key not in aliases:
                continue
            if any(group['id'] == group_id for group in verified):
                continue
            verified.append({
                'id': group_id,
                'name': f'手动覆盖 {group_id}',
                'type_label': '手动指定',
                'group_count': 0,
                'episode_count': 0,
                'description': '',
                'season_episodes': 0,
            })
        return verified

    @staticmethod
    def __subscription_exists(mediainfo, meta) -> bool:
        """查宿主是否已存在该订阅；检查失败时按未订阅处理，避免误跳过。"""
        try:
            return bool(SubscribeChain.exists(mediainfo=mediainfo, meta=meta))
        except Exception as err:
            logger.debug(f"订阅存在性检查失败，按未订阅处理：{str(err)}")
            return False

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
        try:
            episode_numbers = sorted({int(episode) for episode in episodes})
        except (TypeError, ValueError):
            episode_numbers = []
        if len(episode_numbers) > 1:
            resource_season_text = (f"S{season:02d}E{episode_numbers[0]:02d}"
                                    f"-E{episode_numbers[-1]:02d}")
        elif episode_numbers:
            resource_season_text = f"S{season:02d}E{episode_numbers[0]:02d}"
        else:
            resource_season_text = f"S{season:02d}"
        main_seasons_text = summarize_seasons(getattr(mediainfo, 'seasons', None))

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

        platform_hits = detect_platforms(title, self.__platform_tokens())
        platform = platform_hits[0]['key'] if platform_hits else 'UNKNOWN'
        platform_token = platform_hits[0]['token'] if platform_hits else ''
        status = season_matches(getattr(mediainfo, 'seasons', None), season, episodes)
        if status == 'unknown' and not allow_unknown:
            self.__record_retry(state, result, rss_url, 'TMDB 季集信息暂缺')
            return
        tmdbid = getattr(mediainfo, 'tmdb_id', None) or media_id

        item = state['pending'].get(key)
        # 查宿主订阅状态：用户手动订阅过、或旧版本留下的订阅也要跳过。
        # 每个季只在首次入池时检查一次，避免逐条 RSS 重复查询。
        if not item and self.__subscription_exists(mediainfo, meta):
            if key not in state['handled']:
                state['handled'].append(key)
            logger.info(f"{getattr(mediainfo, 'title_year', None) or title} 已存在订阅，跳过入池")
            return
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
                'resource_season_text': resource_season_text,
                'main_seasons_text': main_seasons_text,
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
            'platform_token': platform_token,
            'platform_hits': [hit['token'] for hit in platform_hits],
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
                              platform=winner.get('platform_token') or winner.get('platform'))
            return

        subscribe_id, error, detail = self.__create_subscription(item, winner)
        if error:
            self.__finalize(state, key, item, 'failed', reason=detail or error,
                            platform=winner.get('platform_token') or winner.get('platform'))
            self.__notify('自定义订阅 · 订阅失败', f"{item.get('title')}：{detail or error}")
            return
        self.__finalize(state, key, item, 'subscribed', reason=reason,
                        platform=winner.get('platform_token') or winner.get('platform'), subscribe_id=subscribe_id)
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
                'include': build_include(winner.get('platform_token'), winner.get('team')),
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
                        f"平台={winner.get('platform_token') or winner.get('platform')} "
                        f"include={kwargs['include']} 剧集组={item.get('episode_group') or '无'}")
            return subscribe_id, '', ''
        except Exception as err:
            logger.error(f"添加订阅异常：{str(err)} - {traceback.format_exc()}")
            return None, 'exception', str(err)

    def __refresh_unknown_platforms(self, state: Dict[str, Any]) -> int:
        """按当前平台词表重刷已有 UNKNOWN 候选；已识别平台保持不变。"""
        tokens = self.__platform_tokens()
        refreshed = 0
        for item in state['pending'].values():
            refreshed += reidentify_platforms(item.get('candidates') or [], tokens)
        if refreshed:
            logger.info(f"按当前平台词表重新识别 {refreshed} 条 UNKNOWN 候选")
        return refreshed

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
        state['last_run']['reidentified'] = 0

        # 用户补充自定义平台缩写后，点刷新即可只重刷已有的 UNKNOWN 候选
        try:
            state['last_run']['reidentified'] = self.__refresh_unknown_platforms(state)
        except Exception as err:
            logger.error(f"重刷未识别平台失败：{str(err)}")

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
            "tier1_platforms": self._tier1_platforms,
            "tier2_platforms": self._tier2_platforms,
            "tier3_platforms": self._tier3_platforms,
            "tier2_unconditional": self._tier2_unconditional,
            "custom_platforms": self._custom_platforms,
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
