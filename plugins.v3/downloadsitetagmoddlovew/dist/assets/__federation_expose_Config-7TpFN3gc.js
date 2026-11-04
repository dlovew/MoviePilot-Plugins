import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,withModifiers:_withModifiers} = await importShared('vue');


const _hoisted_1 = { class: "plugin-config" };

const {computed,reactive,ref} = await importShared('vue');



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
 * 下载任务分类与标签插件的 V3 联邦配置组件。
 *
 * 配置读取只依赖宿主注入的 initialConfig，保存统一通过 emit('save') 交给宿主；
 * 调用插件自定义 API 时使用实例作用域的 pluginId，不硬编码类名，以支持插件分身。
 */
const props = __props;

const emit = __emit;

const scheduleTypes = ['禁用', '计划任务', '固定间隔'];
const intervalUnits = ['分钟', '小时'];

const defaultConfig = {
  name: '',
  enable: false,
  interval: '禁用',
  interval_cron: '5 4 * * *',
  interval_time: 6,
  interval_unit: '小时',
  enable_media_tag: false,
  enable_tag: false,
  enable_category: false,
  enable_del_tags: false,
  downloaders: [],
  all_downloaders: [],
  all_cat: [],
  all_cat_rename: [],
  onlyonce: false,
  rename_type: false,
  path_rename: '',
  catprefix: '',
  siteprefix: '',
  tracker_mappings_str: '',
};

const config = reactive({ ...defaultConfig, ...(props.initialConfig || {}) });
const form = ref(null);
const isFormValid = ref(true);
const error = ref(null);
const saving = ref(false);
const pluginId = computed(() => props.pluginId || props.sourcePluginId || config.id || '');

function notifyClose() {
  emit('close');
}

async function saveConfig() {
  if (!isFormValid.value) {
    error.value = '请修正表单错误';
    return
  }
  saving.value = true;
  error.value = null;
  try {
    // V3 宿主统一 PUT plugin/{id} 保存配置，组件不自行调用配置端点
    emit('save', { ...config });
  } catch (err) {
    error.value = err?.message || '保存配置失败';
  } finally {
    saving.value = false;
  }
}

function resetForm() {
  Object.keys(props.initialConfig || {}).forEach(key => {
    config[key] = props.initialConfig[key];
  });
  form.value?.resetValidation?.();
}

async function resetCategories() {
  if (!pluginId.value) {
    error.value = '未获取到插件实例 ID，无法重置二级分类';
    return
  }
  try {
    const response = await props.api.post(`plugin/${pluginId.value}/reset_categories`);
    if (response?.all_cat_rename) {
      config.all_cat_rename = [...response.all_cat_rename];
    }
    if (response?.all_cat) {
      config.all_cat = [...response.all_cat];
    }
    error.value = response?.message || '二级分类已重置';
  } catch (err) {
    error.value = err?.message || '重置二级分类失败';
  }
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_card_item = _resolveComponent("v-card-item");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_checkbox = _resolveComponent("v-checkbox");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_VCronField = _resolveComponent("VCronField");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_form = _resolveComponent("v-form");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, null, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_item, null, {
          append: _withCtx(() => [
            _createVNode(_component_v_btn, {
              icon: "",
              color: "primary",
              variant: "text",
              onClick: notifyClose
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
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(config.name), 1)
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_text, { class: "overflow-y-auto" }, {
          default: _withCtx(() => [
            (error.value)
              ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 0,
                  type: "error",
                  class: "mb-4"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(error.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_v_form, {
              ref_key: "form",
              ref: form,
              modelValue: isFormValid.value,
              "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((isFormValid).value = $event)),
              onSubmit: _withModifiers(saveConfig, ["prevent"])
            }, {
              default: _withCtx(() => [
                _cache[19] || (_cache[19] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-bold mt-4 mb-2" }, "基本设置", -1)),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "3"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_switch, {
                          modelValue: config.enable,
                          "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((config.enable) = $event)),
                          label: "启用插件",
                          color: "primary",
                          "persistent-hint": "",
                          inset: ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "3"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_checkbox, {
                          modelValue: config.enable_tag,
                          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.enable_tag) = $event)),
                          label: "自动站点标签",
                          color: "primary"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "3"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_checkbox, {
                          modelValue: config.enable_media_tag,
                          "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.enable_media_tag) = $event)),
                          label: "自动剧名标签",
                          color: "primary"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "3"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_checkbox, {
                          modelValue: config.enable_category,
                          "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.enable_category) = $event)),
                          label: "自动设置分类",
                          color: "primary"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_checkbox, {
                          modelValue: config.onlyonce,
                          "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.onlyonce) = $event)),
                          label: "补全下载历史的标签与分类(一次性任务)",
                          color: "primary",
                          inset: ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "3"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_checkbox, {
                          modelValue: config.enable_del_tags,
                          "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.enable_del_tags) = $event)),
                          label: "自动删除未使用标签",
                          color: "primary"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, null, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_switch, {
                          modelValue: config.rename_type,
                          "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.rename_type) = $event)),
                          label: "自定义",
                          color: "primary",
                          "persistent-hint": "",
                          inset: ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_divider),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, { cols: "12" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_select, {
                          modelValue: config.downloaders,
                          "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.downloaders) = $event)),
                          items: config.all_downloaders,
                          label: "下载器",
                          placeholder: "请选择下载器",
                          "item-text": "title",
                          "item-value": "value",
                          multiple: "",
                          chips: ""
                        }, null, 8, ["modelValue", "items"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.catprefix,
                          "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.catprefix) = $event)),
                          label: "自定义分类前缀",
                          placeholder: "默认为空"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.siteprefix,
                          "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.siteprefix) = $event)),
                          label: "自定义站点标签前缀",
                          placeholder: "默认为空"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "6",
                      md: "3"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_select, {
                          modelValue: config.interval,
                          "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.interval) = $event)),
                          items: scheduleTypes,
                          label: "定时任务类型"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    (config.interval === '计划任务')
                      ? (_openBlock(), _createBlock(_component_v_col, {
                          key: 0,
                          cols: "6",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCronField, {
                              modelValue: config.interval_cron,
                              "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.interval_cron) = $event)),
                              label: "计划任务设置 CRON表达式",
                              hint: "设置日志清理的执行周期，如：5 4 * * * (每天凌晨4:05)",
                              "persistent-hint": "",
                              density: "compact"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true),
                    (config.interval === '固定间隔')
                      ? (_openBlock(), _createBlock(_component_v_col, {
                          key: 1,
                          cols: "6",
                          md: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: config.interval_time,
                              "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.interval_time) = $event)),
                              modelModifiers: { number: true },
                              label: "固定间隔",
                              type: "number",
                              placeholder: "输入间隔时间"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true),
                    (config.interval === '固定间隔')
                      ? (_openBlock(), _createBlock(_component_v_col, {
                          key: 2,
                          cols: "6",
                          md: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_select, {
                              modelValue: config.interval_unit,
                              "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.interval_unit) = $event)),
                              items: intervalUnits,
                              label: "单位",
                              density: "compact"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_divider, { class: "my-4" }),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, { cols: "12" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_alert, {
                          type: "info",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                            _createTextVNode(" 以下为 tracker 映射规则，您可以根据需要修改或添加新的规则。 ", -1)
                          ]))]),
                          _: 1
                        })
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_row, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_col, { cols: "12" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_textarea, {
                          modelValue: config.tracker_mappings_str,
                          "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.tracker_mappings_str) = $event)),
                          label: "Tracker域名映射规则",
                          rows: "6",
                          "auto-grow": "",
                          placeholder: "每行一个映射，格式：tracker域名 -> 映射域名\n例如：chdbits.xyz -> ptchdbits.co",
                          hint: "支持的分隔符：->, →, :, ：，空格",
                          "persistent-hint": ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_divider, { class: "my-4" }),
                (!config.rename_type)
                  ? (_openBlock(), _createBlock(_component_v_row, { key: 0 }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_col, { cols: "12" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_row, null, {
                              default: _withCtx(() => [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(config.all_cat, (category, index) => {
                                  return (_openBlock(), _createBlock(_component_v_col, {
                                    key: index,
                                    cols: "12",
                                    md: "3"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_text_field, {
                                        modelValue: config.all_cat_rename[index],
                                        "onUpdate:modelValue": $event => ((config.all_cat_rename[index]) = $event),
                                        label: category,
                                        placeholder: category
                                      }, null, 8, ["modelValue", "onUpdate:modelValue", "label", "placeholder"])
                                    ]),
                                    _: 2
                                  }, 1024))
                                }), 128))
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }))
                  : (_openBlock(), _createBlock(_component_v_row, { key: 1 }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_col, { cols: "12" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_textarea, {
                              modelValue: config.path_rename,
                              "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.path_rename) = $event)),
                              label: "按路径自定义分类",
                              hint: "每一行一个配置，中间以#分隔：路径#分类名称",
                              "persistent-hint": "",
                              variant: "filled",
                              "auto-grow": ""
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    })),
                _createVNode(_component_v_divider, { class: "my-4" })
              ]),
              _: 1
            }, 8, ["modelValue"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_actions, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              color: "secondary",
              onClick: resetForm
            }, {
              default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                _createTextVNode("重置", -1)
              ]))]),
              _: 1
            }),
            (!config.rename_type)
              ? (_openBlock(), _createBlock(_component_v_btn, {
                  key: 0,
                  color: "warning",
                  onClick: resetCategories
                }, {
                  default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                    _createTextVNode("重置二级分类", -1)
                  ]))]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_v_spacer),
            _createVNode(_component_v_btn, {
              color: "primary",
              disabled: !isFormValid.value,
              loading: saving.value,
              onClick: saveConfig
            }, {
              default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                _createTextVNode("保存配置", -1)
              ]))]),
              _: 1
            }, 8, ["disabled", "loading"])
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
