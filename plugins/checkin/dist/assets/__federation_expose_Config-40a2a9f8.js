import { importShared } from './__federation_fn_import-054b33c3.js';
import { n as normalizeConfig, S as SITE_META, v as validateConfig, c as clone } from './plugin-c8525d6a.js';

const Config_vue_vue_type_style_index_0_scoped_72d21190_lang = '';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,unref:_unref,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "checkin-config pa-4" };
const _hoisted_2 = { class: "d-flex align-center justify-space-between mb-4" };
const _hoisted_3 = { class: "d-flex ga-2" };
const _hoisted_4 = { class: "d-flex justify-end ga-2" };

const {reactive,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
  api: {
    type: Object,
    default: () => ({}),
  },
  saving: {
    type: Boolean,
    default: false,
  },
  lastSavedAt: {
    type: Number,
    default: 0,
  },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const config = reactive(normalizeConfig());
const message = ref('');
const messageType = ref('info');
const submitted = ref(false);

function applyConfig(value = {}) {
  Object.assign(config, normalizeConfig(value));
}

function saveConfig() {
  const errors = validateConfig(config);
  if (errors.length) {
    submitted.value = false;
    message.value = errors.join('；');
    messageType.value = 'error';
    return
  }

  submitted.value = true;
  message.value = '正在保存配置...';
  messageType.value = 'info';
  emit('save', clone(config));
}

watch(() => props.initialConfig, applyConfig, { immediate: true, deep: true });

watch(() => props.saving, (saving) => {
  if (submitted.value && saving) {
    message.value = '正在保存配置...';
    messageType.value = 'info';
  }
});

watch(() => props.lastSavedAt, (value) => {
  if (!value || !submitted.value) return
  submitted.value = false;
  message.value = '配置已保存';
  messageType.value = 'success';
});

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_textarea = _resolveComponent("v-textarea");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[8] || (_cache[8] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "text-h6" }, "自用签到工具配置"),
        _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "配置站点账号、Cookie 和定时执行参数。")
      ], -1)),
      _createElementVNode("div", _hoisted_3, [
        _createVNode(_component_v_btn, {
          icon: "mdi-view-dashboard-outline",
          variant: "tonal",
          onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
        }),
        _createVNode(_component_v_btn, {
          icon: "mdi-close",
          variant: "text",
          onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
        })
      ])
    ]),
    (message.value)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
          type: messageType.value,
          variant: "tonal",
          class: "mb-4"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(message.value), 1)
          ]),
          _: 1
        }, 8, ["type"]))
      : _createCommentVNode("", true),
    _createVNode(_component_v_card, {
      variant: "outlined",
      class: "mb-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, null, {
          default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
            _createTextVNode("通用设置", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_row, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: config.enabled,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.enabled) = $event)),
                      label: "启用插件",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: config.notify,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.notify) = $event)),
                      label: "执行后通知",
                      inset: ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.cron,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.cron) = $event)),
                      label: "执行时间",
                      hint: "例如：10 8 * * *",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "6",
                  md: "1"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.timeout,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.timeout) = $event)),
                      modelModifiers: { number: true },
                      label: "超时",
                      type: "number",
                      min: "5"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "6",
                  md: "2"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.retry_count,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.retry_count) = $event)),
                      modelModifiers: { number: true },
                      label: "重试次数",
                      type: "number",
                      min: "1"
                    }, null, 8, ["modelValue"])
                  ]),
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
    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(Object.values(_unref(SITE_META)), (site) => {
      return (_openBlock(), _createBlock(_component_v_card, {
        key: site.key,
        variant: "outlined",
        class: "mb-4"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                icon: site.icon,
                color: site.color,
                class: "mr-2"
              }, null, 8, ["icon", "color"]),
              _createTextVNode(" " + _toDisplayString(site.title) + " ", 1),
              _createVNode(_component_v_chip, {
                class: "ml-3",
                size: "small",
                variant: "tonal"
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(site.mode), 1)
                ]),
                _: 2
              }, 1024)
            ]),
            _: 2
          }, 1024),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_row, null, {
                default: _withCtx(() => [
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_switch, {
                        modelValue: config.sites[site.key].enabled,
                        "onUpdate:modelValue": $event => ((config.sites[site.key].enabled) = $event),
                        label: "启用站点",
                        inset: ""
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_switch, {
                        modelValue: config.sites[site.key].use_proxy,
                        "onUpdate:modelValue": $event => ((config.sites[site.key].use_proxy) = $event),
                        label: "使用代理",
                        inset: ""
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  (site.key === 'flzt' || site.key === 'ypojie')
                    ? (_openBlock(), _createBlock(_component_v_col, {
                        key: 0,
                        cols: "12",
                        md: "3"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_text_field, {
                            modelValue: config.sites[site.key].email,
                            "onUpdate:modelValue": $event => ((config.sites[site.key].email) = $event),
                            label: site.key === 'flzt' ? '邮箱' : '账号',
                            autocomplete: "off"
                          }, null, 8, ["modelValue", "onUpdate:modelValue", "label"])
                        ]),
                        _: 2
                      }, 1024))
                    : _createCommentVNode("", true),
                  (site.key === 'flzt' || site.key === 'ypojie')
                    ? (_openBlock(), _createBlock(_component_v_col, {
                        key: 1,
                        cols: "12",
                        md: "3"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_text_field, {
                            modelValue: config.sites[site.key].password,
                            "onUpdate:modelValue": $event => ((config.sites[site.key].password) = $event),
                            label: "密码",
                            type: "password",
                            autocomplete: "new-password"
                          }, null, 8, ["modelValue", "onUpdate:modelValue"])
                        ]),
                        _: 2
                      }, 1024))
                    : _createCommentVNode("", true),
                  (site.key === 'right_forum')
                    ? (_openBlock(), _createBlock(_component_v_col, {
                        key: 2,
                        cols: "12",
                        md: "6"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_textarea, {
                            modelValue: config.sites[site.key].cookie,
                            "onUpdate:modelValue": $event => ((config.sites[site.key].cookie) = $event),
                            class: "cookie-textarea",
                            label: "Cookie",
                            rows: "3",
                            "no-resize": ""
                          }, null, 8, ["modelValue", "onUpdate:modelValue"])
                        ]),
                        _: 2
                      }, 1024))
                    : _createCommentVNode("", true)
                ]),
                _: 2
              }, 1024)
            ]),
            _: 2
          }, 1024)
        ]),
        _: 2
      }, 1024))
    }), 128)),
    _createElementVNode("div", _hoisted_4, [
      _createVNode(_component_v_btn, {
        variant: "tonal",
        "prepend-icon": "mdi-restore",
        onClick: _cache[7] || (_cache[7] = $event => (applyConfig(props.initialConfig)))
      }, {
        default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
          _createTextVNode("重置", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_v_btn, {
        "prepend-icon": "mdi-content-save-outline",
        loading: __props.saving,
        disabled: __props.saving,
        onClick: saveConfig
      }, {
        default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
          _createTextVNode("保存", -1)
        ]))]),
        _: 1
      }, 8, ["loading", "disabled"])
    ])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-72d21190"]]);

export { Config as default };
