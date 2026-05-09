import { importShared } from './__federation_fn_import-054b33c3.js';
import { f as flztSiteMeta, r as rightForumSiteMeta, c as cloneConfig, n as normalizeSiteConfig, v as validateRightForumCookie } from './index-7b3b5f0c.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const Config_vue_vue_type_style_index_0_scoped_118de66a_lang = '';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,unref:_unref,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "flzt-config" };
const _hoisted_2 = { class: "flzt-topbar" };
const _hoisted_3 = { class: "flzt-config__switch-item" };
const _hoisted_4 = { class: "flzt-config__switch-item" };
const _hoisted_5 = { class: "flzt-config__site-switches mb-4" };
const _hoisted_6 = { class: "flzt-config__site-switches mb-4" };

const {computed,reactive,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
  api: {
    type: [Function, Object],
    default: null,
  },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;
const saving = ref(false);
const message = ref('');
const messageType = ref('success');

const defaultConfig = {
  enabled: false,
  notify: true,
  cron: '10 8 * * *',
  timeout: 10,
  retry_count: 3,
  sites: {
    flzt: {
      enabled: false,
        use_proxy: false,
      email: '',
      password: '',
    },
    right_forum: {
      enabled: false,
        use_proxy: false,
      cookie: '',
    },
  },
};

function normalizeConfig(value = {}) {
  const normalized = {
    ...cloneConfig(defaultConfig),
    ...cloneConfig(value || {}),
  };
  normalized.sites = normalizeSiteConfig({
    ...defaultConfig.sites,
    ...(value?.sites || {}),
  });
  return normalized
}

const config = reactive(normalizeConfig(props.initialConfig));

watch(
  () => props.initialConfig,
  (value) => {
    Object.assign(config, normalizeConfig(value));
  },
  { deep: true }
);

function resetConfig() {
  Object.assign(config, normalizeConfig(props.initialConfig));
  message.value = '已恢复为当前已保存配置';
  messageType.value = 'info';
}

async function saveConfig() {
  saving.value = true;
  message.value = '';
  try {
    if (config.sites.right_forum.enabled) {
      const cookieError = validateRightForumCookie(config.sites.right_forum.cookie);
      if (cookieError) {
        throw new Error(cookieError)
      }
    }
    emit('save', cloneConfig(config));
    message.value = '配置已提交';
    messageType.value = 'success';
  } catch (error) {
    message.value = error?.message || '配置保存失败';
    messageType.value = 'error';
  } finally {
    saving.value = false;
  }
}

const cronHint = computed(() => '示例：10 8 * * * 表示每天 08:10 自动执行签到');
const enabledSiteCount = computed(() => Object.values(config.sites || {}).filter(site => site.enabled).length);

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_group = _resolveComponent("v-btn-group");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_textarea = _resolveComponent("v-textarea");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[17] || (_cache[17] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "flzt-topbar__title" }, "自用签到工具配置"),
        _createElementVNode("div", { class: "flzt-topbar__subtitle" }, "保留常用配置与站点开关")
      ], -1)),
      _createVNode(_component_v_btn_group, {
        variant: "tonal",
        density: "compact"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_btn, {
            color: "primary",
            onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                icon: "mdi-view-dashboard-outline",
                class: "mr-1"
              }),
              _cache[14] || (_cache[14] = _createTextVNode(" 状态页 ", -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            color: "primary",
            onClick: resetConfig
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                icon: "mdi-restore",
                class: "mr-1"
              }),
              _cache[15] || (_cache[15] = _createTextVNode(" 重置 ", -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            color: "primary",
            loading: saving.value,
            onClick: saveConfig
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                icon: "mdi-content-save-outline",
                class: "mr-1"
              }),
              _cache[16] || (_cache[16] = _createTextVNode(" 保存 ", -1))
            ]),
            _: 1
          }, 8, ["loading"]),
          _createVNode(_component_v_btn, {
            color: "primary",
            onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, { icon: "mdi-close" })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    (message.value)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
          type: messageType.value,
          variant: "tonal",
          density: "comfortable",
          class: "mb-4"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(message.value), 1)
          ]),
          _: 1
        }, 8, ["type"]))
      : _createCommentVNode("", true),
    _createVNode(_component_v_row, { class: "ga-0 flzt-config__grid" }, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, { cols: "12" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              variant: "outlined",
              class: "mb-4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-cog-outline",
                      class: "mr-2",
                      color: "primary"
                    }),
                    _cache[18] || (_cache[18] = _createTextVNode(" 通用 ", -1))
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _cache[22] || (_cache[22] = _createElementVNode("div", { class: "flzt-config__section-title" }, "基础开关", -1)),
                    _createVNode(_component_v_row, { class: "flzt-config__field-row" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_3, [
                              _cache[19] || (_cache[19] = _createElementVNode("div", { class: "flzt-config__field-label" }, "插件状态", -1)),
                              _createVNode(_component_v_switch, {
                                modelValue: config.enabled,
                                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.enabled) = $event)),
                                color: "primary",
                                label: "启用插件",
                                inset: "",
                                "hide-details": ""
                              }, null, 8, ["modelValue"])
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_4, [
                              _cache[20] || (_cache[20] = _createElementVNode("div", { class: "flzt-config__field-label" }, "通知", -1)),
                              _createVNode(_component_v_switch, {
                                modelValue: config.notify,
                                "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.notify) = $event)),
                                color: "primary",
                                label: "执行后发送通知",
                                inset: "",
                                "hide-details": ""
                              }, null, 8, ["modelValue"])
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "4"
                        }, {
                          default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                            _createElementVNode("div", { class: "flzt-config__switch-item flzt-config__switch-item--muted" }, [
                              _createElementVNode("div", { class: "flzt-config__field-label" }, "网络"),
                              _createElementVNode("div", { class: "flzt-config__switch-text" }, "代理已改为各站点单独配置")
                            ], -1)
                          ]))]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }),
                    _cache[23] || (_cache[23] = _createElementVNode("div", { class: "flzt-config__section-title mt-2" }, "执行参数", -1)),
                    _createVNode(_component_v_row, { class: "flzt-config__field-row" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "6",
                          lg: "5"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: config.cron,
                              "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.cron) = $event)),
                              label: "执行时间",
                              variant: "outlined",
                              "prepend-inner-icon": "mdi-calendar-clock-outline",
                              hint: cronHint.value,
                              "persistent-hint": ""
                            }, null, 8, ["modelValue", "hint"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          sm: "6",
                          lg: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: config.timeout,
                              "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.timeout) = $event)),
                              modelModifiers: { number: true },
                              label: "超时（秒）",
                              type: "number",
                              variant: "outlined",
                              min: "5",
                              max: "60",
                              "prepend-inner-icon": "mdi-timer-sand"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          sm: "6",
                          lg: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: config.retry_count,
                              "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.retry_count) = $event)),
                              modelModifiers: { number: true },
                              label: "重试次数",
                              type: "number",
                              variant: "outlined",
                              min: "1",
                              max: "10",
                              "prepend-inner-icon": "mdi-refresh-circle"
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
                      class: "mt-2"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode("当前已启用 " + _toDisplayString(enabledSiteCount.value) + " 个站点", 1)
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
        _createVNode(_component_v_col, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              variant: "outlined",
              class: "h-100"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: _unref(flztSiteMeta).icon,
                      class: "mr-2",
                      color: _unref(flztSiteMeta).color
                    }, null, 8, ["icon", "color"]),
                    _createTextVNode(" " + _toDisplayString(_unref(flztSiteMeta).title), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, { class: "flzt-config__site-card" }, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_5, [
                      _createVNode(_component_v_switch, {
                        modelValue: config.sites.flzt.enabled,
                        "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.sites.flzt.enabled) = $event)),
                        color: _unref(flztSiteMeta).color,
                        label: "启用该站点",
                        inset: "",
                        "hide-details": ""
                      }, null, 8, ["modelValue", "color"]),
                      _createVNode(_component_v_switch, {
                        modelValue: config.sites.flzt.use_proxy,
                        "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.sites.flzt.use_proxy) = $event)),
                        color: _unref(flztSiteMeta).color,
                        label: "该站点使用代理",
                        inset: "",
                        "hide-details": ""
                      }, null, 8, ["modelValue", "color"])
                    ]),
                    _createVNode(_component_v_row, { class: "flzt-config__field-row" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_col, { cols: "12" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: config.sites.flzt.email,
                              "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.sites.flzt.email) = $event)),
                              label: "邮箱",
                              variant: "outlined",
                              "prepend-inner-icon": "mdi-email-outline"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, { cols: "12" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: config.sites.flzt.password,
                              "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.sites.flzt.password) = $event)),
                              label: "密码",
                              variant: "outlined",
                              type: "password",
                              "prepend-inner-icon": "mdi-lock-outline"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }),
                    _cache[24] || (_cache[24] = _createElementVNode("div", { class: "flzt-config__hint" }, "使用账号密码登录并签到。", -1))
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_v_col, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              variant: "outlined",
              class: "h-100"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: _unref(rightForumSiteMeta).icon,
                      class: "mr-2",
                      color: _unref(rightForumSiteMeta).color
                    }, null, 8, ["icon", "color"]),
                    _createTextVNode(" " + _toDisplayString(_unref(rightForumSiteMeta).title), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, { class: "flzt-config__site-card" }, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_6, [
                      _createVNode(_component_v_switch, {
                        modelValue: config.sites.right_forum.enabled,
                        "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.sites.right_forum.enabled) = $event)),
                        color: _unref(rightForumSiteMeta).color,
                        label: "启用该站点",
                        inset: "",
                        "hide-details": ""
                      }, null, 8, ["modelValue", "color"]),
                      _createVNode(_component_v_switch, {
                        modelValue: config.sites.right_forum.use_proxy,
                        "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.sites.right_forum.use_proxy) = $event)),
                        color: _unref(rightForumSiteMeta).color,
                        label: "该站点使用代理",
                        inset: "",
                        "hide-details": ""
                      }, null, 8, ["modelValue", "color"])
                    ]),
                    _createVNode(_component_v_textarea, {
                      modelValue: config.sites.right_forum.cookie,
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.sites.right_forum.cookie) = $event)),
                      label: "Cookie",
                      variant: "outlined",
                      rows: "4",
                      "max-rows": "6",
                      "auto-grow": "",
                      "prepend-inner-icon": "mdi-cookie-outline",
                      class: "flzt-config__cookie-textarea"
                    }, null, 8, ["modelValue"]),
                    _cache[25] || (_cache[25] = _createElementVNode("div", { class: "flzt-config__hint mt-3" }, "请先在浏览器登录并复制完整 Cookie。", -1))
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
    })
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-118de66a"]]);

export { Config as default };
