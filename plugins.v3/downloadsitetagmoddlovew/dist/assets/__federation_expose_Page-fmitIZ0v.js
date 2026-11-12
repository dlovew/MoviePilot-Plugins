import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createVNode:_createVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "plugin-page" };
const _hoisted_2 = { class: "d-flex flex-wrap mb-4" };
const _hoisted_3 = { class: "text-body-2" };
const _hoisted_4 = { class: "text-body-2" };
const _hoisted_5 = { class: "text-body-2" };
const _hoisted_6 = {
  key: 3,
  class: "text-body-2"
};

const {computed,onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: [Object, Function], required: true },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  show_switch: { type: Boolean, default: true },
},
  emits: ['close', 'switch', 'action', 'layout'],
  setup(__props, { emit: __emit }) {

/**
 * 数据页（联邦 ./Page）。
 *
 * V3 宿主在 render_mode=vue 时固定加载 ./Page，插件若不暴露该组件，
 * 数据页就会显示「无法加载组件」。这里提供插件运行状态概览，并保留
 * 切换到设置页的入口。插件 ID 一律使用宿主注入的实例 ID，支持分身。
 */
const props = __props;

const emit = __emit;

const loading = ref(false);
const error = ref('');
const status = ref(null);
const pluginId = computed(() => props.pluginId || props.sourcePluginId || '');

const scheduleText = computed(() => {
  const value = status.value;
  if (!value) return '-'
  if (value.interval === '计划任务') return `计划任务 · ${value.interval_cron}`
  if (value.interval === '固定间隔') return `固定间隔 · 每 ${value.interval_time} ${value.interval_unit}`
  return value.interval || '禁用'
});

const featureList = computed(() => Object.entries(status.value?.features || {}));

async function loadStatus() {
  if (!pluginId.value) {
    error.value = '未获取到插件实例 ID，无法读取运行状态';
    return
  }
  loading.value = true;
  error.value = '';
  try {
    status.value = await props.api.get(`plugin/${pluginId.value}/status`);
  } catch (err) {
    error.value = err?.message || '读取插件状态失败';
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  emit('layout', { maxWidth: '52rem' });
  void loadStatus();
});

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_card_item = _resolveComponent("v-card-item");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_progress_linear = _resolveComponent("v-progress-linear");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, null, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_item, null, {
          append: _withCtx(() => [
            (__props.show_switch)
              ? (_openBlock(), _createBlock(_component_v_btn, {
                  key: 0,
                  color: "primary",
                  variant: "text",
                  "prepend-icon": "mdi-cog",
                  onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
                }, {
                  default: _withCtx(() => [...(_cache[2] || (_cache[2] = [
                    _createTextVNode(" 设置 ", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_v_btn, {
              icon: "",
              variant: "text",
              onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, null, {
                  default: _withCtx(() => [...(_cache[3] || (_cache[3] = [
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
              default: _withCtx(() => [...(_cache[4] || (_cache[4] = [
                _createTextVNode("下载任务分类与标签 · 运行状态", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            (error.value)
              ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 0,
                  type: "warning",
                  class: "mb-4"
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
                  class: "mb-4"
                }))
              : _createCommentVNode("", true),
            (status.value)
              ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                  _createVNode(_component_v_row, { dense: "" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_col, {
                        cols: "12",
                        sm: "6"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_list_item, {
                            title: "插件状态",
                            subtitle: status.value.enabled ? '已启用' : '未启用'
                          }, {
                            prepend: _withCtx(() => [
                              _createVNode(_component_v_icon, {
                                color: status.value.enabled ? 'success' : 'grey'
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(status.value.enabled ? 'mdi-check-circle' : 'mdi-pause-circle'), 1)
                                ]),
                                _: 1
                              }, 8, ["color"])
                            ]),
                            _: 1
                          }, 8, ["subtitle"])
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_col, {
                        cols: "12",
                        sm: "6"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_list_item, {
                            title: "定时策略",
                            subtitle: scheduleText.value
                          }, {
                            prepend: _withCtx(() => [
                              _createVNode(_component_v_icon, { color: "primary" }, {
                                default: _withCtx(() => [...(_cache[5] || (_cache[5] = [
                                  _createTextVNode("mdi-clock-outline", -1)
                                ]))]),
                                _: 1
                              })
                            ]),
                            _: 1
                          }, 8, ["subtitle"])
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_divider, { class: "my-3" }),
                  _cache[10] || (_cache[10] = _createElementVNode("div", { class: "text-subtitle-2 mb-2" }, "已启用功能", -1)),
                  _createElementVNode("div", _hoisted_2, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(featureList.value, ([name, enabled]) => {
                      return (_openBlock(), _createBlock(_component_v_chip, {
                        key: name,
                        class: "ma-1",
                        color: enabled ? 'primary' : undefined,
                        variant: enabled ? 'flat' : 'outlined',
                        size: "small"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_icon, { start: "" }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(enabled ? 'mdi-check' : 'mdi-close'), 1)
                            ]),
                            _: 2
                          }, 1024),
                          _createTextVNode(" " + _toDisplayString(name), 1)
                        ]),
                        _: 2
                      }, 1032, ["color", "variant"]))
                    }), 128))
                  ]),
                  _createVNode(_component_v_divider, { class: "my-3" }),
                  _createVNode(_component_v_row, { dense: "" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_col, {
                        cols: "12",
                        sm: "4"
                      }, {
                        default: _withCtx(() => [
                          _cache[6] || (_cache[6] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "已选下载器", -1)),
                          _createElementVNode("div", _hoisted_3, _toDisplayString((status.value.selected_downloaders || []).join('、') || '未选择'), 1)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_col, {
                        cols: "12",
                        sm: "4"
                      }, {
                        default: _withCtx(() => [
                          _cache[7] || (_cache[7] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "可用下载器", -1)),
                          _createElementVNode("div", _hoisted_4, _toDisplayString((status.value.downloaders || []).join('、') || '无'), 1)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_col, {
                        cols: "12",
                        sm: "4"
                      }, {
                        default: _withCtx(() => [
                          _cache[8] || (_cache[8] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "二级分类", -1)),
                          _createElementVNode("div", _hoisted_5, _toDisplayString(status.value.category_count) + " 项 · " + _toDisplayString(status.value.rename_type), 1)
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
                    default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                      _createTextVNode(" 配置、二级分类重命名与 Tracker 映射请在「设置」页调整；修改后由定时服务或一次性任务生效。 ", -1)
                    ]))]),
                    _: 1
                  })
                ], 64))
              : (!loading.value && !error.value)
                ? (_openBlock(), _createElementBlock("div", _hoisted_6, "暂无运行状态数据。"))
                : _createCommentVNode("", true)
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_actions, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_spacer),
            _createVNode(_component_v_btn, {
              variant: "text",
              "prepend-icon": "mdi-refresh",
              onClick: loadStatus
            }, {
              default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
                _createTextVNode("刷新", -1)
              ]))]),
              _: 1
            })
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

export { _sfc_main as default };
