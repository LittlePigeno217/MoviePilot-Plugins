import { importShared } from './__federation_fn_import-054b33c3.js';
import { c as cloneConfig } from './flzt-e78fda74.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const Config_vue_vue_type_style_index_0_scoped_903984ec_lang = '';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "flzt-config" };
const _hoisted_2 = { class: "flzt-topbar" };

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
  use_proxy: false,
  cron: '10 8 * * *',
  email: '',
  password: '',
  timeout: 10,
  retry_count: 3,
};

const config = reactive({ ...defaultConfig, ...cloneConfig(props.initialConfig) });

watch(
  () => props.initialConfig,
  (value) => {
    Object.assign(config, defaultConfig, cloneConfig(value));
  },
  { deep: true }
);

function resetConfig() {
  Object.assign(config, defaultConfig, cloneConfig(props.initialConfig));
  message.value = '已恢复为当前已保存配置';
  messageType.value = 'info';
}

async function saveConfig() {
  saving.value = true;
  message.value = '';
  try {
    emit('save', { ...config });
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

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_group = _resolveComponent("v-btn-group");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[13] || (_cache[13] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "flzt-topbar__title" }, "FLZT 自动签到配置"),
        _createElementVNode("div", { class: "flzt-topbar__subtitle" }, "配置账号、定时策略和通知行为")
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
              _cache[10] || (_cache[10] = _createTextVNode(" 状态页 ", -1))
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
              _cache[11] || (_cache[11] = _createTextVNode(" 重置 ", -1))
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
              _cache[12] || (_cache[12] = _createTextVNode(" 保存 ", -1))
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
    _createVNode(_component_v_row, null, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, {
          cols: "12",
          lg: "6"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              class: "h-100",
              variant: "outlined"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-account-cog-outline",
                      class: "mr-2",
                      color: "primary"
                    }),
                    _cache[14] || (_cache[14] = _createTextVNode(" 基础与账号 ", -1))
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: config.enabled,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.enabled) = $event)),
                      color: "primary",
                      label: "启用插件",
                      inset: ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_switch, {
                      modelValue: config.notify,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.notify) = $event)),
                      color: "primary",
                      label: "执行后发送通知",
                      inset: ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_switch, {
                      modelValue: config.use_proxy,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.use_proxy) = $event)),
                      color: "primary",
                      label: "使用系统代理",
                      inset: ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_text_field, {
                      modelValue: config.email,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.email) = $event)),
                      label: "FLZT 邮箱",
                      variant: "outlined",
                      "prepend-inner-icon": "mdi-email-outline",
                      hint: "填写 FLZT 登录邮箱",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_text_field, {
                      modelValue: config.password,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.password) = $event)),
                      label: "FLZT 密码",
                      variant: "outlined",
                      type: "password",
                      "prepend-inner-icon": "mdi-lock-outline",
                      hint: "保存后由 MoviePilot 后端用于登录签到",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
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
          lg: "6"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              class: "h-100",
              variant: "outlined"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-timer-cog-outline",
                      class: "mr-2",
                      color: "success"
                    }),
                    _cache[15] || (_cache[15] = _createTextVNode(" 调度与重试 ", -1))
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.cron,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.cron) = $event)),
                      label: "Cron 表达式",
                      variant: "outlined",
                      "prepend-inner-icon": "mdi-calendar-clock-outline",
                      hint: cronHint.value,
                      "persistent-hint": ""
                    }, null, 8, ["modelValue", "hint"]),
                    _createVNode(_component_v_text_field, {
                      modelValue: config.timeout,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.timeout) = $event)),
                      modelModifiers: { number: true },
                      label: "请求超时（秒）",
                      type: "number",
                      variant: "outlined",
                      min: "5",
                      max: "60",
                      "prepend-inner-icon": "mdi-timer-sand"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_text_field, {
                      modelValue: config.retry_count,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.retry_count) = $event)),
                      modelModifiers: { number: true },
                      label: "失败重试次数",
                      type: "number",
                      variant: "outlined",
                      min: "1",
                      max: "10",
                      "prepend-inner-icon": "mdi-refresh-circle"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_alert, {
                      type: "info",
                      variant: "tonal",
                      class: "mt-2"
                    }, {
                      default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                        _createTextVNode(" 插件流程：登录 `FLZT` → 调用 `/api/v1/user/checkIn` → 保存历史 → 可选发送通知。 ", -1)
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
        })
      ]),
      _: 1
    })
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-903984ec"]]);

export { Config as default };
