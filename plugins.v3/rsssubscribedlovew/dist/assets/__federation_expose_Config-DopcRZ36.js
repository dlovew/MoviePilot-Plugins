import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "rss-config" };

const {computed,onMounted,reactive,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  api: { type: [Object, Function], required: true },
  initialConfig: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
},
  emits: ['save', 'close', 'switch', 'layout'],
  setup(__props, { emit: __emit }) {

/**
 * 自定义订阅番剧魔改版 —— V3 联邦配置组件（./Config）。
 *
 * 配置只依赖宿主注入的 initialConfig，保存统一 emit('save') 交给宿主；
 * 平台多选项通过实例作用域的 /platform_options 读取，接口失败时按当前配置兜底。
 * 插件 ID 一律使用宿主注入值，支持分身。
 */
const props = __props;

const emit = __emit;

const defaultConfig = {
  enabled: false,
  notify: false,
  onlyonce: false,
  clear: false,
  proxy: false,
  filter: false,
  cron: '*/30 * * * *',
  collect_window_hours: 24,
  address: '',
  include: '',
  exclude: '',
  size_range: '',
  save_path: '',
  auto_detect_episode_group: true,
  auto_select_single_group: false,
  episode_group_overrides: '',
  pending_group_action: 'notify',
  retry_unrecognized: true,
  notify_unrecognized: true,
  dry_run: false,
  tier1_platforms: [],
  tier2_platforms: [],
  tier3_platforms: [],
  tier2_unconditional: true,
  custom_platforms: '',
};

const config = reactive({ ...defaultConfig, ...(props.initialConfig || {}) });
const platformOptions = ref([]);
const optionsError = ref('');
const saving = ref(false);

const pluginId = computed(() => props.pluginId || props.sourcePluginId || '');
const pendingGroupItems = [
  { title: '通知并继续挂起', value: 'notify' },
  { title: '直接忽略', value: 'ignore' },
];

function fallbackOptions() {
  const names = new Set([
    ...(config.tier1_platforms || []),
    ...(config.tier2_platforms || []),
    ...(config.tier3_platforms || []),
    ...String(config.custom_platforms || '').split('\n').map(s => s.trim()).filter(Boolean),
  ]);
  return [...names].map(name => ({ title: name, value: name }))
}

async function loadPlatformOptions() {
  optionsError.value = '';
  if (!pluginId.value) {
    platformOptions.value = fallbackOptions();
    return
  }
  try {
    const res = await props.api.get(`plugin/${pluginId.value}/platform_options`);
    const items = Array.isArray(res) ? res : (res?.data || res?.items || []);
    platformOptions.value = Array.isArray(items) && items.length ? items : fallbackOptions();
  } catch (err) {
    optionsError.value = err?.message || '平台选项读取失败，已使用当前配置';
    platformOptions.value = fallbackOptions();
  }
}

function refreshOptions() {
  // 自定义缩写填入后点保存前也能在下拉里看到
  const fromApi = new Set(platformOptions.value.map(item => item.value ?? item.title));
  for (const item of fallbackOptions()) {
    if (!fromApi.has(item.value)) platformOptions.value.push(item);
  }
}

function saveConfig() {
  saving.value = true;
  try {
    emit('save', { ...config });
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  emit('layout', { maxWidth: '60rem' });
  void loadPlatformOptions();
});

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_card_item = _resolveComponent("v-card-item");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, { flat: "" }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_item, null, {
          append: _withCtx(() => [
            _createVNode(_component_v_btn, {
              color: "primary",
              variant: "text",
              "prepend-icon": "mdi-cog",
              onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
            }, {
              default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                _createTextVNode("数据页", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_btn, {
              icon: "",
              variant: "text",
              onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, null, {
                  default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                    _createTextVNode("mdi-close", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, null, {
              default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                _createTextVNode("自定义订阅番剧 · 设置", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            (optionsError.value)
              ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 0,
                  type: "warning",
                  variant: "tonal",
                  density: "compact",
                  class: "mb-3"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(optionsError.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _cache[20] || (_cache[20] = _createElementVNode("div", { class: "text-subtitle-2 mb-2" }, "基础", -1)),
            _createVNode(_component_v_row, { dense: "" }, {
              default: _withCtx(() => [
                (_openBlock(), _createElementBlock(_Fragment, null, _renderList([
            { key: 'enabled', label: '启用插件' },
            { key: 'notify', label: '发送通知' },
            { key: 'onlyonce', label: '立即运行一次' },
            { key: 'clear', label: '清空候选池与历史' },
            { key: 'proxy', label: '使用代理' },
            { key: 'filter', label: '应用订阅过滤规则' },
          ], (item) => {
                  return _createVNode(_component_v_col, {
                    key: item.key,
                    cols: "12",
                    sm: "6",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_switch, {
                        modelValue: config[item.key],
                        "onUpdate:modelValue": $event => ((config[item.key]) = $event),
                        label: item.label,
                        color: "primary",
                        density: "compact",
                        "hide-details": ""
                      }, null, 8, ["modelValue", "onUpdate:modelValue", "label"])
                    ]),
                    _: 2
                  }, 1024)
                }), 64))
              ]),
              _: 1
            }),
            _createVNode(_component_v_row, {
              dense: "",
              class: "mt-2"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.cron,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.cron) = $event)),
                      label: "执行周期（5 位 cron，留空则每 30 分钟）",
                      placeholder: "*/30 * * * *",
                      density: "compact",
                      "hide-details": "auto",
                      hint: "例如 0 */6 * * * 表示每 6 小时",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.collect_window_hours,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.collect_window_hours) = $event)),
                      modelModifiers: { number: true },
                      label: "候选窗口（小时）",
                      type: "number",
                      min: "1",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_v_row, {
              dense: "",
              class: "mt-2"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_textarea, {
                      modelValue: config.address,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.address) = $event)),
                      label: "RSS 链接（每行一个，全部都会处理）",
                      rows: "3",
                      "auto-grow": "",
                      density: "compact",
                      "hide-details": "",
                      placeholder: "https://...\nhttps://..."
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_textarea, {
                      modelValue: config.include,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.include) = $event)),
                      label: "包含规则（正则，决定哪些资源入池）",
                      rows: "2",
                      "auto-grow": "",
                      density: "compact",
                      "hide-details": "",
                      placeholder: "(?=.*月新番)(?=.*E01)"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_textarea, {
                      modelValue: config.exclude,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.exclude) = $event)),
                      label: "排除规则（正则）",
                      rows: "2",
                      "auto-grow": "",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.size_range,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.size_range) = $event)),
                      label: "体积范围（GiB，如 0.5-8）",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.save_path,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.save_path) = $event)),
                      label: "订阅保存目录（留空自动）",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _cache[21] || (_cache[21] = _createElementVNode("div", { class: "text-subtitle-2 mt-5 mb-2" }, "决策", -1)),
            _createVNode(_component_v_row, { dense: "" }, {
              default: _withCtx(() => [
                (_openBlock(), _createElementBlock(_Fragment, null, _renderList([
            { key: 'auto_detect_episode_group', label: '自动探测剧集组' },
            { key: 'auto_select_single_group', label: '唯一候选组自动选用' },
            { key: 'retry_unrecognized', label: '识别失败进入重试队列' },
            { key: 'notify_unrecognized', label: '识别失败发送通知' },
            { key: 'dry_run', label: '试运行（只预览不订阅）' },
          ], (item) => {
                  return _createVNode(_component_v_col, {
                    key: item.key,
                    cols: "12",
                    sm: "6",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_switch, {
                        modelValue: config[item.key],
                        "onUpdate:modelValue": $event => ((config[item.key]) = $event),
                        label: item.label,
                        color: "primary",
                        density: "compact",
                        "hide-details": ""
                      }, null, 8, ["modelValue", "onUpdate:modelValue", "label"])
                    ]),
                    _: 2
                  }, 1024)
                }), 64)),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_select, {
                      modelValue: config.pending_group_action,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.pending_group_action) = $event)),
                      items: pendingGroupItems,
                      label: "到期未选剧集组",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_textarea, {
                      modelValue: config.episode_group_overrides,
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.episode_group_overrides) = $event)),
                      label: "剧集组覆盖（每行 媒体ID=组ID）",
                      rows: "2",
                      "auto-grow": "",
                      density: "compact",
                      "hide-details": "",
                      placeholder: "12345=5f3a..."
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _cache[22] || (_cache[22] = _createElementVNode("div", { class: "text-subtitle-2 mt-5 mb-2" }, "平台分层", -1)),
            _createVNode(_component_v_row, { dense: "" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_select, {
                      modelValue: config.tier1_platforms,
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.tier1_platforms) = $event)),
                      items: platformOptions.value,
                      multiple: "",
                      chips: "",
                      "closable-chips": "",
                      label: "Tier1 首选平台（按等效单集体积选最小）",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue", "items"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_select, {
                      modelValue: config.tier2_platforms,
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.tier2_platforms) = $event)),
                      items: platformOptions.value,
                      multiple: "",
                      chips: "",
                      "closable-chips": "",
                      label: "Tier2 兜底平台",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue", "items"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_select, {
                      modelValue: config.tier3_platforms,
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.tier3_platforms) = $event)),
                      items: platformOptions.value,
                      multiple: "",
                      chips: "",
                      "closable-chips": "",
                      label: "Tier3 其余兜底平台",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue", "items"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: config.tier2_unconditional,
                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.tier2_unconditional) = $event)),
                      label: "Tier2 无条件优先（不与 Tier3 比体积）",
                      color: "primary",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_textarea, {
                      modelValue: config.custom_platforms,
                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.custom_platforms) = $event)),
                      onBlur: refreshOptions,
                      label: "自定义平台缩写（每行一个，按资源标题里的写法）",
                      rows: "2",
                      "auto-grow": "",
                      density: "compact",
                      "hide-details": "",
                      placeholder: "ABEMA"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_v_alert, {
              type: "info",
              variant: "tonal",
              density: "compact",
              class: "mt-4"
            }, {
              default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                _createTextVNode(" 入池完全由「包含规则」决定，插件不判断季首或合集。识别成功后按「媒体身份 + 季」归并候选， 窗口从该季第一条入池资源起算；到期按分层规则比较等效单集体积，只创建一次整季订阅。 平台缩写取自资源标题原文，新增平台先在自定义框填写并保存即可在下拉中勾选。 ", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_actions, { class: "justify-end" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              variant: "text",
              onClick: loadPlatformOptions
            }, {
              default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
                _createTextVNode("刷新平台选项", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_btn, {
              color: "primary",
              variant: "tonal",
              loading: saving.value,
              "prepend-icon": "mdi-content-save",
              onClick: saveConfig
            }, {
              default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
                _createTextVNode(" 保存 ", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ]),
          _: 1
        })
      ]),
      _: 1
    })
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-cb766197"]]);

export { Config as default };
