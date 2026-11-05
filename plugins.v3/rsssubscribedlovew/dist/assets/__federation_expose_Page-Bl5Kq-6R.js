import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock,createElementVNode:_createElementVNode,createVNode:_createVNode,renderList:_renderList,Fragment:_Fragment,normalizeStyle:_normalizeStyle} = await importShared('vue');


const _hoisted_1 = { class: "rss-status text-body-2 text-center" };
const _hoisted_2 = { key: 0 };
const _hoisted_3 = { class: "rss-metrics" };
const _hoisted_4 = {
  key: 2,
  class: "rss-section"
};
const _hoisted_5 = { class: "rss-section-title" };
const _hoisted_6 = { class: "rss-header" };
const _hoisted_7 = ["href"];
const _hoisted_8 = {
  key: 1,
  class: "rss-title"
};
const _hoisted_9 = { class: "rss-actions" };
const _hoisted_10 = { class: "rss-line" };
const _hoisted_11 = { class: "rss-group-pick" };
const _hoisted_12 = ["href"];
const _hoisted_13 = {
  key: 0,
  class: "rss-line"
};
const _hoisted_14 = { class: "rss-section" };
const _hoisted_15 = { class: "rss-section-title" };
const _hoisted_16 = { class: "rss-row" };
const _hoisted_17 = {
  key: 1,
  class: "rss-poster-placeholder"
};
const _hoisted_18 = { class: "rss-row-body" };
const _hoisted_19 = { class: "rss-header" };
const _hoisted_20 = ["href"];
const _hoisted_21 = {
  key: 1,
  class: "rss-title"
};
const _hoisted_22 = { class: "rss-actions" };
const _hoisted_23 = { class: "rss-line" };
const _hoisted_24 = { class: "rss-chips" };
const _hoisted_25 = {
  key: 0,
  class: "rss-line"
};
const _hoisted_26 = {
  key: 0,
  class: "rss-copy"
};
const _hoisted_27 = ["value"];
const _hoisted_28 = {
  key: 0,
  class: "rss-empty"
};
const _hoisted_29 = { class: "rss-section" };
const _hoisted_30 = { class: "rss-section-title" };
const _hoisted_31 = { class: "rss-chips" };
const _hoisted_32 = {
  key: 0,
  class: "rss-empty"
};
const _hoisted_33 = { class: "rss-section" };
const _hoisted_34 = { class: "rss-section-title" };
const _hoisted_35 = {
  key: 0,
  class: "rss-filter-note"
};
const _hoisted_36 = { class: "rss-chips rss-filters" };
const _hoisted_37 = { class: "rss-row" };
const _hoisted_38 = {
  key: 1,
  class: "rss-poster-placeholder"
};
const _hoisted_39 = { class: "rss-row-body" };
const _hoisted_40 = { class: "rss-header" };
const _hoisted_41 = ["href"];
const _hoisted_42 = {
  key: 1,
  class: "rss-title"
};
const _hoisted_43 = { class: "rss-actions" };
const _hoisted_44 = { class: "rss-line" };
const _hoisted_45 = {
  key: 0,
  class: "rss-empty"
};

const {computed,nextTick,onMounted,reactive,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: [Object, Function], required: true },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  show_switch: { type: Boolean, default: true },
  nativeSubscribe: { type: [Object, Function], default: null },
},
  emits: ['close', 'switch', 'action', 'layout'],
  setup(__props, { emit: __emit }) {

/**
 * 自定义订阅番剧魔改版 —— V3 联邦数据页（./Page）。
 *
 * 数据通过实例作用域的 /runtime_data 读取；所有按钮沿用后端既有 GET 端点，
 * 参数拼在 query 上，操作完成后自行刷新，不依赖宿主的整页重载。
 * onMounted 声明宿主弹窗宽度，只影响本插件。
 */
const props = __props;

const emit = __emit;

const data = ref(null);
const loading = ref(false);
const busy = ref(false);
const error = ref('');
const pageRef = ref(null);
const pageWidth = ref(0);

const showAllHistory = ref(false);
const historyFilter = ref('');
const groupSelections = reactive({});

const pluginId = computed(() => props.pluginId || props.sourcePluginId || '');
const waiting = computed(() => data.value?.pending || []);
const groupPending = computed(() => waiting.value.filter(
  item => item.group_status === 'mismatch' && !item.episode_group
));
const history = computed(() => data.value?.history || []);
const retry = computed(() => data.value?.retry || []);
const config = computed(() => data.value?.config || {});
const lastRun = computed(() => data.value?.last_run || {});

const historyFilters = [
  { label: '全部', value: '' },
  { label: '已订阅', value: 'subscribed' },
  { label: '失败', value: 'failed' },
  { label: '忽略', value: 'ignored' },
  { label: '预览', value: 'dry_run' },
];

const matchedHistory = computed(() => historyFilter.value
  ? history.value.filter(item => String(item.action || '') === historyFilter.value)
  : history.value);
const shownHistory = computed(() => matchedHistory.value.slice(0, showAllHistory.value ? 200 : 10));

function tmdbUrl(id) {
  const value = String(id || '').trim();
  return /^\d+$/.test(value) ? `https://www.themoviedb.org/tv/${value}` : ''
}

function sizeText(value) {
  return typeof value === 'number' && isFinite(value)
    ? `${(value / 1024 ** 3).toFixed(2)} GiB/集`
    : '体积未知'
}

function platformChips(candidates) {
  const grouped = new Map();
  for (const candidate of candidates || []) {
    const platform = String(candidate.platform_token || candidate.platform || '').trim();
    const team = String(candidate.team || '').trim();
    const unknown = !platform || platform.toUpperCase() === 'UNKNOWN';
    const label = platform && team ? `${platform}-${team}` : (platform || team || '未知平台');
    const size = typeof candidate.normalized_size === 'number' ? candidate.normalized_size : null;
    const current = grouped.get(label);
    if (!current || (size !== null && (current.size === null || size < current.size))) {
      grouped.set(label, { label, unknown, size, title: String(candidate.title || '') });
    }
  }
  return [...grouped.values()].slice(0, 8)
}

function unknownTitles(item) {
  return platformChips(item?.candidates)
    .filter(chip => chip.unknown && chip.title)
    .map(chip => chip.title)
    .slice(0, 3)
}

function groupItems(item) {
  return (item.group_candidates || []).map(group => {
    const meta = [
      group.type_label,
      group.group_count ? `${group.group_count} 季` : '',
      group.episode_count ? `${group.episode_count} 集` : '',
      group.season_episodes ? `该季 ${group.season_episodes} 集` : '',
    ].filter(Boolean).join(' · ');
    return {
      title: `${group.name || group.id}${meta ? ' · ' + meta : ''} · ID ${group.id}`,
      value: String(group.id),
    }
  })
}

function statusLabel(item) {
  return item.group_status === 'mismatch' && !item.episode_group
    ? '待选剧集组' : '等待窗口到期'
}

/** 按最长信息行测量自然宽度，让记录卡片与宿主弹窗一起随内容变宽。 */
function measureWidth() {
  nextTick(() => {
    const root = pageRef.value;
    if (!root) return
    let longest = 0;
    for (const el of root.querySelectorAll('.rss-line, .rss-status')) {
      longest = Math.max(longest, el.scrollWidth || 0);
    }
    const viewport = typeof window !== 'undefined' ? window.innerWidth : 1200;
    // 封面 64 + 间距 14 + 卡片左右内边距 24 + 页面左右内边距 40
    const needed = Math.max(longest, 260) + 64 + 14 + 24 + 40;
    const cap = Math.max(viewport - 48, 320);
    pageWidth.value = Math.max(Math.min(needed, cap), 480);
    // 弹窗比记录卡片再宽一点
    emit('layout', { maxWidth: `${pageWidth.value + 16}px` });
  });
}

async function loadData() {
  if (!pluginId.value) {
    error.value = '未获取到插件实例 ID，无法读取运行状态';
    return
  }
  loading.value = true;
  error.value = '';
  try {
    const res = await props.api.get(`plugin/${pluginId.value}/runtime_data`);
    data.value = res?.data && !Array.isArray(res) ? res.data : res;
  } catch (err) {
    error.value = err?.message || '读取运行状态失败';
  } finally {
    loading.value = false;
    measureWidth();
  }
}

async function callApi(path, params = {}) {
  if (busy.value) return
  busy.value = true;
  error.value = '';
  try {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
    ).toString();
    const url = `plugin/${pluginId.value}/${path}${query ? '?' + query : ''}`;
    await props.api.get(url);
    emit('action');
    await loadData();
  } catch (err) {
    error.value = err?.message || '操作失败';
  } finally {
    busy.value = false;
  }
}

async function applyGroup(key) {
  const groupId = groupSelections[key];
  if (!groupId) return
  await callApi('set_episode_group', { key, group_id: groupId });
}

function onCopyFocus(event) {
  event.target.select();
}

onMounted(() => {
  // 加载期间的兜底值；数据渲染后由 measureWidth 按实际内容覆盖
  emit('layout', { maxWidth: '48rem' });
  void loadData();
});

return (_ctx, _cache) => {
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_progress_linear = _resolveComponent("v-progress-linear");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_img = _resolveComponent("v-img");

  return (_openBlock(), _createElementBlock("div", {
    ref_key: "pageRef",
    ref: pageRef,
    class: "rss-page",
    style: _normalizeStyle(pageWidth.value ? { width: pageWidth.value + 'px' } : null)
  }, [
    (error.value)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
          type: "warning",
          variant: "tonal",
          density: "compact",
          class: "mb-3"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(error.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (loading.value)
      ? (_openBlock(), _createBlock(_component_v_progress_linear, {
          key: 1,
          indeterminate: "",
          color: "primary",
          class: "mb-3"
        }))
      : _createCommentVNode("", true),
    _createVNode(_component_v_card, {
      variant: "tonal",
      rounded: "lg",
      class: "pa-3 mb-4"
    }, {
      default: _withCtx(() => [
        _createElementVNode("div", _hoisted_1, [
          _createTextVNode(" v" + _toDisplayString(data.value?.version || '-') + "　最近运行 " + _toDisplayString(lastRun.value.time || '尚未运行') + "　入池 " + _toDisplayString(lastRun.value.ingested || 0) + "　结算 " + _toDisplayString(lastRun.value.settled || 0) + "　窗口 " + _toDisplayString(config.value.collect_window_hours || 24) + "h　" + _toDisplayString(config.value.dry_run ? '试运行' : '正常'), 1),
          (lastRun.value.reidentified)
            ? (_openBlock(), _createElementBlock("span", _hoisted_2, "　重识别 " + _toDisplayString(lastRun.value.reidentified), 1))
            : _createCommentVNode("", true)
        ]),
        _createElementVNode("div", _hoisted_3, [
          _createVNode(_component_v_chip, {
            size: "small",
            color: "primary",
            variant: "flat"
          }, {
            default: _withCtx(() => [
              _createTextVNode("等待中 " + _toDisplayString(waiting.value.length), 1)
            ]),
            _: 1
          }),
          _createVNode(_component_v_chip, {
            size: "small",
            color: groupPending.value.length ? 'warning' : 'grey',
            variant: "flat"
          }, {
            default: _withCtx(() => [
              _createTextVNode("待选剧集组 " + _toDisplayString(groupPending.value.length), 1)
            ]),
            _: 1
          }, 8, ["color"]),
          _createVNode(_component_v_chip, {
            size: "small",
            color: retry.value.length ? 'error' : 'grey',
            variant: "flat"
          }, {
            default: _withCtx(() => [
              _createTextVNode("待重试 " + _toDisplayString(retry.value.length), 1)
            ]),
            _: 1
          }, 8, ["color"]),
          _createVNode(_component_v_chip, {
            size: "small",
            color: "grey",
            variant: "flat"
          }, {
            default: _withCtx(() => [
              _createTextVNode("已处理 " + _toDisplayString(data.value?.handled_count || 0), 1)
            ]),
            _: 1
          })
        ]),
        _createVNode(_component_v_card_actions, { class: "justify-center" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              size: "small",
              color: "primary",
              variant: "tonal",
              disabled: busy.value,
              onClick: _cache[0] || (_cache[0] = $event => (callApi('run_check')))
            }, {
              default: _withCtx(() => [...(_cache[5] || (_cache[5] = [
                _createTextVNode("刷新全部 RSS", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode(_component_v_btn, {
              size: "small",
              color: "primary",
              variant: "tonal",
              disabled: busy.value,
              onClick: _cache[1] || (_cache[1] = $event => (callApi('settle')))
            }, {
              default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
                _createTextVNode("结算全部候选", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            (__props.show_switch)
              ? (_openBlock(), _createBlock(_component_v_btn, {
                  key: 0,
                  size: "small",
                  variant: "text",
                  "prepend-icon": "mdi-cog",
                  onClick: _cache[2] || (_cache[2] = $event => (emit('switch')))
                }, {
                  default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
                    _createTextVNode("设置", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_v_btn, {
              icon: "",
              size: "small",
              variant: "text",
              onClick: _cache[3] || (_cache[3] = $event => (emit('close')))
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, null, {
                  default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
                    _createTextVNode("mdi-close", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    (groupPending.value.length)
      ? (_openBlock(), _createElementBlock("section", _hoisted_4, [
          _createElementVNode("div", _hoisted_5, "待选择剧集组（" + _toDisplayString(groupPending.value.length) + "）", 1),
          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(groupPending.value, (item) => {
            return (_openBlock(), _createBlock(_component_v_card, {
              key: item.key,
              variant: "tonal",
              color: "warning",
              rounded: "lg",
              class: "pa-3 mb-2"
            }, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_6, [
                  (tmdbUrl(item.tmdbid))
                    ? (_openBlock(), _createElementBlock("a", {
                        key: 0,
                        href: tmdbUrl(item.tmdbid),
                        target: "_blank",
                        rel: "noopener noreferrer",
                        class: "rss-title-link"
                      }, _toDisplayString(item.title || item.key) + " ↗", 9, _hoisted_7))
                    : (_openBlock(), _createElementBlock("span", _hoisted_8, _toDisplayString(item.title || item.key), 1)),
                  _createElementVNode("div", _hoisted_9, [
                    _createVNode(_component_v_btn, {
                      size: "small",
                      variant: "text",
                      color: "grey",
                      disabled: busy.value,
                      onClick: $event => (callApi('ignore_group', { key: item.key }))
                    }, {
                      default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                        _createTextVNode("忽略", -1)
                      ]))]),
                      _: 1
                    }, 8, ["disabled", "onClick"])
                  ])
                ]),
                _createElementVNode("div", _hoisted_10, _toDisplayString(item.resource_season_text || '-') + " → TMDB " + _toDisplayString(item.main_seasons_text || '-') + "　候选组 " + _toDisplayString((item.group_candidates || []).length) + " 个　入池 " + _toDisplayString(item.first_seen || '-'), 1),
                _createElementVNode("div", _hoisted_11, [
                  _createVNode(_component_v_select, {
                    modelValue: groupSelections[item.key],
                    "onUpdate:modelValue": $event => ((groupSelections[item.key]) = $event),
                    items: groupItems(item),
                    label: "选择剧集组",
                    density: "compact",
                    "hide-details": "",
                    clearable: ""
                  }, null, 8, ["modelValue", "onUpdate:modelValue", "items"]),
                  _createVNode(_component_v_btn, {
                    size: "small",
                    color: "primary",
                    variant: "tonal",
                    disabled: busy.value || !groupSelections[item.key],
                    onClick: $event => (applyGroup(item.key))
                  }, {
                    default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
                      _createTextVNode("选用并结算", -1)
                    ]))]),
                    _: 1
                  }, 8, ["disabled", "onClick"]),
                  (tmdbUrl(item.tmdbid))
                    ? (_openBlock(), _createElementBlock("a", {
                        key: 0,
                        href: tmdbUrl(item.tmdbid) + '/episodes',
                        target: "_blank",
                        rel: "noopener noreferrer",
                        class: "rss-sub-link"
                      }, "季集 / 剧集组 ↗", 8, _hoisted_12))
                    : _createCommentVNode("", true)
                ]),
                (!groupItems(item).length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_13, "无候选组，可在设置页「剧集组覆盖」按 媒体ID=组ID 填写后刷新，或忽略"))
                  : _createCommentVNode("", true)
              ]),
              _: 2
            }, 1024))
          }), 128))
        ]))
      : _createCommentVNode("", true),
    _createElementVNode("section", _hoisted_14, [
      _createElementVNode("div", _hoisted_15, "等待中（" + _toDisplayString(waiting.value.length) + "）", 1),
      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(waiting.value, (item) => {
        return (_openBlock(), _createBlock(_component_v_card, {
          key: item.key,
          variant: "tonal",
          rounded: "lg",
          class: "pa-3 mb-2"
        }, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_16, [
              (item.poster)
                ? (_openBlock(), _createBlock(_component_v_img, {
                    key: 0,
                    src: item.poster,
                    width: "64",
                    "aspect-ratio": "2/3",
                    cover: "",
                    class: "rounded-lg rss-poster"
                  }, null, 8, ["src"]))
                : (_openBlock(), _createElementBlock("div", _hoisted_17)),
              _createElementVNode("div", _hoisted_18, [
                _createElementVNode("div", _hoisted_19, [
                  (tmdbUrl(item.tmdbid))
                    ? (_openBlock(), _createElementBlock("a", {
                        key: 0,
                        href: tmdbUrl(item.tmdbid),
                        target: "_blank",
                        rel: "noopener noreferrer",
                        class: "rss-title-link"
                      }, _toDisplayString(item.title || item.key) + " ↗", 9, _hoisted_20))
                    : (_openBlock(), _createElementBlock("span", _hoisted_21, _toDisplayString(item.title || item.key), 1)),
                  _createElementVNode("div", _hoisted_22, [
                    _createVNode(_component_v_btn, {
                      size: "small",
                      color: "primary",
                      variant: "tonal",
                      disabled: busy.value,
                      onClick: $event => (callApi('settle', { key: item.key }))
                    }, {
                      default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
                        _createTextVNode("立即结算", -1)
                      ]))]),
                      _: 1
                    }, 8, ["disabled", "onClick"]),
                    _createVNode(_component_v_btn, {
                      size: "small",
                      variant: "text",
                      color: "grey",
                      disabled: busy.value,
                      onClick: $event => (callApi('ignore_key', { key: item.key }))
                    }, {
                      default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
                        _createTextVNode("忽略", -1)
                      ]))]),
                      _: 1
                    }, 8, ["disabled", "onClick"])
                  ])
                ]),
                _createElementVNode("div", _hoisted_23, _toDisplayString(item.resource_season_text || '-') + "　入池 " + _toDisplayString(item.first_seen || '-') + "　共 " + _toDisplayString((item.candidates || []).length) + " 个候选　" + _toDisplayString(statusLabel(item)), 1),
                _createElementVNode("div", _hoisted_24, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(platformChips(item.candidates), (chip) => {
                    return (_openBlock(), _createBlock(_component_v_chip, {
                      key: chip.label,
                      size: "small",
                      color: chip.unknown ? 'warning' : 'primary',
                      variant: chip.unknown ? 'flat' : 'tonal'
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(chip.unknown ? '⚠ ' : '') + _toDisplayString(chip.label) + " · " + _toDisplayString(sizeText(chip.size)), 1)
                      ]),
                      _: 2
                    }, 1032, ["color", "variant"]))
                  }), 128)),
                  (!platformChips(item.candidates).length)
                    ? (_openBlock(), _createElementBlock("span", _hoisted_25, "暂无候选"))
                    : _createCommentVNode("", true)
                ]),
                (unknownTitles(item).length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_26, [
                      _cache[13] || (_cache[13] = _createElementVNode("div", { class: "rss-line" }, "未识别平台：点击下面标题即可选中复制缩写，填到设置页「自定义平台缩写」", -1)),
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(unknownTitles(item), (title, index) => {
                        return (_openBlock(), _createElementBlock("input", {
                          key: index,
                          value: title,
                          readonly: "",
                          class: "rss-copy-input",
                          onFocus: onCopyFocus
                        }, null, 40, _hoisted_27))
                      }), 128))
                    ]))
                  : _createCommentVNode("", true)
              ])
            ])
          ]),
          _: 2
        }, 1024))
      }), 128)),
      (!waiting.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_28, "暂无等待中的资源"))
        : _createCommentVNode("", true)
    ]),
    _createElementVNode("section", _hoisted_29, [
      _createElementVNode("div", _hoisted_30, "识别失败待重试（" + _toDisplayString(retry.value.length) + "）", 1),
      _createElementVNode("div", _hoisted_31, [
        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(retry.value.slice(0, 30), (item, index) => {
          return (_openBlock(), _createBlock(_component_v_chip, {
            key: index,
            size: "small",
            variant: "tonal"
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(item.title || '-') + "（重试 " + _toDisplayString(item.attempts || 0) + " 次） ", 1)
            ]),
            _: 2
          }, 1024))
        }), 128)),
        (!retry.value.length)
          ? (_openBlock(), _createElementBlock("span", _hoisted_32, "无"))
          : _createCommentVNode("", true)
      ])
    ]),
    _createElementVNode("section", _hoisted_33, [
      _createElementVNode("div", _hoisted_34, [
        _createTextVNode(" 决策记录（" + _toDisplayString(showAllHistory.value ? '全部' : '最近') + " " + _toDisplayString(shownHistory.value.length) + " / 共 " + _toDisplayString(matchedHistory.value.length) + "） ", 1),
        (historyFilter.value)
          ? (_openBlock(), _createElementBlock("span", _hoisted_35, "· 已筛选 " + _toDisplayString(historyFilter.value), 1))
          : _createCommentVNode("", true)
      ]),
      _createElementVNode("div", _hoisted_36, [
        (_openBlock(), _createElementBlock(_Fragment, null, _renderList(historyFilters, (item) => {
          return _createVNode(_component_v_chip, {
            key: item.value,
            size: "small",
            color: historyFilter.value === item.value ? 'primary' : 'grey',
            variant: historyFilter.value === item.value ? 'flat' : 'tonal',
            onClick: $event => (historyFilter.value = item.value)
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(item.label), 1)
            ]),
            _: 2
          }, 1032, ["color", "variant", "onClick"])
        }), 64)),
        (matchedHistory.value.length > 10)
          ? (_openBlock(), _createBlock(_component_v_chip, {
              key: 0,
              size: "small",
              variant: "tonal",
              onClick: _cache[4] || (_cache[4] = $event => (showAllHistory.value = !showAllHistory.value))
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(showAllHistory.value ? '收起' : '展开全部'), 1)
              ]),
              _: 1
            }))
          : _createCommentVNode("", true)
      ]),
      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(shownHistory.value, (record) => {
        return (_openBlock(), _createBlock(_component_v_card, {
          key: record.id || record.time,
          variant: "tonal",
          rounded: "lg",
          class: "pa-3 mb-2"
        }, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_37, [
              (record.poster)
                ? (_openBlock(), _createBlock(_component_v_img, {
                    key: 0,
                    src: record.poster,
                    width: "64",
                    "aspect-ratio": "2/3",
                    cover: "",
                    class: "rounded-lg rss-poster"
                  }, null, 8, ["src"]))
                : (_openBlock(), _createElementBlock("div", _hoisted_38)),
              _createElementVNode("div", _hoisted_39, [
                _createElementVNode("div", _hoisted_40, [
                  (tmdbUrl(record.tmdbid))
                    ? (_openBlock(), _createElementBlock("a", {
                        key: 0,
                        href: tmdbUrl(record.tmdbid),
                        target: "_blank",
                        rel: "noopener noreferrer",
                        class: "rss-title-link"
                      }, _toDisplayString(record.title || record.key || '-') + " ↗", 9, _hoisted_41))
                    : (_openBlock(), _createElementBlock("span", _hoisted_42, _toDisplayString(record.title || record.key || '-'), 1)),
                  _createElementVNode("div", _hoisted_43, [
                    _createVNode(_component_v_btn, {
                      size: "small",
                      variant: "text",
                      color: "error",
                      disabled: busy.value,
                      onClick: $event => (callApi('delete_history', { key: record.id || '' }))
                    }, {
                      default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
                        _createTextVNode("删除", -1)
                      ]))]),
                      _: 1
                    }, 8, ["disabled", "onClick"])
                  ])
                ]),
                _createElementVNode("div", _hoisted_44, _toDisplayString(record.resource_season_text || '') + "　" + _toDisplayString(record.time || '-') + "　" + _toDisplayString(record.action || '-') + "　" + _toDisplayString(record.platform || '') + "　" + _toDisplayString(record.reason || record.error || ''), 1)
              ])
            ])
          ]),
          _: 2
        }, 1024))
      }), 128)),
      (!shownHistory.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_45, "暂无决策记录"))
        : _createCommentVNode("", true)
    ])
  ], 4))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-4eff09e8"]]);

export { Page as default };
