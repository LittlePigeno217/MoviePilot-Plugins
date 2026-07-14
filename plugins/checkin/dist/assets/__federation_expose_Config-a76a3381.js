import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, n as normalizeConfig, S as SITE_META, v as validateConfig, c as clone } from './_plugin-vue_export-helper-9f9119c5.js';

const Config_vue_vue_type_style_index_0_scoped_e44c0256_lang = '';

const {createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,normalizeClass:_normalizeClass,createCommentVNode:_createCommentVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,unref:_unref,renderList:_renderList,Fragment:_Fragment,createStaticVNode:_createStaticVNode} = await importShared('vue');


const _hoisted_1 = { class: "checkin-config" };
const _hoisted_2 = { class: "ck-masthead" };
const _hoisted_3 = { class: "ck-tools" };
const _hoisted_4 = { class: "ck-panel ck-sec" };
const _hoisted_5 = { class: "ck-fields" };
const _hoisted_6 = { class: "ck-field ck-field--switch" };
const _hoisted_7 = { class: "ck-field ck-field--switch" };
const _hoisted_8 = { class: "ck-field ck-field--wide" };
const _hoisted_9 = { class: "ck-field" };
const _hoisted_10 = { class: "ck-field" };
const _hoisted_11 = { class: "ck-sec__head ck-sec__head--site" };
const _hoisted_12 = { class: "ck-cfg-badge" };
const _hoisted_13 = { class: "ck-sec__title" };
const _hoisted_14 = { class: "ck-chip ck-chip--muted" };
const _hoisted_15 = {
  key: 0,
  class: "ck-chip ck-chip--seal ck-sec__on"
};
const _hoisted_16 = { class: "ck-fields" };
const _hoisted_17 = { class: "ck-field ck-field--switch" };
const _hoisted_18 = { class: "ck-field ck-field--switch" };
const _hoisted_19 = { class: "ck-field" };
const _hoisted_20 = { class: "ck-field" };
const _hoisted_21 = {
  key: 1,
  class: "ck-field ck-field--full"
};
const _hoisted_22 = { class: "ck-footer" };
const _hoisted_23 = ["disabled"];
const _hoisted_24 = {
  key: 0,
  class: "ck-spin"
};
const _hoisted_25 = {
  key: 1,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  "stroke-width": "2",
  "stroke-linecap": "round",
  "stroke-linejoin": "round",
  width: "16",
  height: "16"
};

const {reactive,ref,watch} = await importShared('vue');

const SEAL = '#c4362e';

const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
  saving: { type: Boolean, default: false },
  lastSavedAt: { type: Number, default: 0 },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

// 自用签到 · 配置页（与数据页同一「朱砂印章」视觉语言）
// 视觉重做，逻辑与校验不变：通用参数 + 三站点账号/Cookie，保存前 validateConfig 校验。
const props = __props;
const emit = __emit;

const config = reactive(normalizeConfig());
const message = ref('');
const messageType = ref('info');
const submitted = ref(false);

const BADGE = { flzt: 'F', right_forum: '恩', ypojie: '易' };
const siteList = Object.values(SITE_META);

function applyConfig(value = {}) {
  Object.assign(config, normalizeConfig(value));
}

function saveConfig() {
  const errors = validateConfig(config);
  if (errors.length) {
    submitted.value = false;
    message.value = errors.join('；');
    messageType.value = 'error';
    return;
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
  if (!value || !submitted.value) return;
  submitted.value = false;
  message.value = '配置已保存';
  messageType.value = 'success';
});

return (_ctx, _cache) => {
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_textarea = _resolveComponent("v-textarea");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("header", _hoisted_2, [
      _cache[10] || (_cache[10] = _createStaticVNode("<div class=\"ck-brand\" data-v-e44c0256><div class=\"ck-seal ck-brand__mark\" data-v-e44c0256><span class=\"ck-seal__text\" data-v-e44c0256>印</span></div><div data-v-e44c0256><div class=\"ck-brand__title\" data-v-e44c0256>自用签到 · 配置</div><div class=\"ck-brand__sub\" data-v-e44c0256>站点账号 · Cookie · 定时参数</div></div></div>", 1)),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("button", {
          class: "ck-btn ck-btn--icon",
          title: "数据页",
          onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
        }, [...(_cache[8] || (_cache[8] = [
          _createStaticVNode("<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" data-v-e44c0256><rect x=\"3\" y=\"3\" width=\"7\" height=\"7\" rx=\"1\" data-v-e44c0256></rect><rect x=\"14\" y=\"3\" width=\"7\" height=\"7\" rx=\"1\" data-v-e44c0256></rect><rect x=\"14\" y=\"14\" width=\"7\" height=\"7\" rx=\"1\" data-v-e44c0256></rect><rect x=\"3\" y=\"14\" width=\"7\" height=\"7\" rx=\"1\" data-v-e44c0256></rect></svg>", 1)
        ]))]),
        _createElementVNode("button", {
          class: "ck-btn ck-btn--icon ck-btn--bare",
          title: "关闭",
          onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
        }, [...(_cache[9] || (_cache[9] = [
          _createElementVNode("svg", {
            viewBox: "0 0 24 24",
            fill: "none",
            stroke: "currentColor",
            "stroke-width": "2",
            "stroke-linecap": "round",
            "stroke-linejoin": "round"
          }, [
            _createElementVNode("path", { d: "M18 6 6 18M6 6l12 12" })
          ], -1)
        ]))])
      ])
    ]),
    (message.value)
      ? (_openBlock(), _createElementBlock("div", {
          key: 0,
          class: _normalizeClass(["ck-notice", `ck-notice--${messageType.value}`])
        }, [
          _cache[11] || (_cache[11] = _createElementVNode("span", { class: "ck-notice__dot" }, null, -1)),
          _createTextVNode(_toDisplayString(message.value), 1)
        ], 2))
      : _createCommentVNode("", true),
    _createElementVNode("section", _hoisted_4, [
      _cache[12] || (_cache[12] = _createElementVNode("div", { class: "ck-sec__head" }, [
        _createElementVNode("span", { class: "ck-sec__bar" }),
        _createTextVNode("通用设置")
      ], -1)),
      _createElementVNode("div", _hoisted_5, [
        _createElementVNode("div", _hoisted_6, [
          _createVNode(_component_v_switch, {
            modelValue: config.enabled,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.enabled) = $event)),
            color: SEAL,
            label: "启用插件",
            inset: "",
            "hide-details": "",
            density: "comfortable"
          }, null, 8, ["modelValue"])
        ]),
        _createElementVNode("div", _hoisted_7, [
          _createVNode(_component_v_switch, {
            modelValue: config.notify,
            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.notify) = $event)),
            color: SEAL,
            label: "执行后通知",
            inset: "",
            "hide-details": "",
            density: "comfortable"
          }, null, 8, ["modelValue"])
        ]),
        _createElementVNode("div", _hoisted_8, [
          _createVNode(_component_v_text_field, {
            modelValue: config.cron,
            "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.cron) = $event)),
            label: "执行时间 (cron)",
            variant: "outlined",
            density: "comfortable",
            hint: "例如：10 8 * * * 表示每天 08:10",
            "persistent-hint": ""
          }, null, 8, ["modelValue"])
        ]),
        _createElementVNode("div", _hoisted_9, [
          _createVNode(_component_v_text_field, {
            modelValue: config.timeout,
            "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.timeout) = $event)),
            modelModifiers: { number: true },
            label: "超时 (秒)",
            type: "number",
            min: "5",
            variant: "outlined",
            density: "comfortable",
            "hide-details": ""
          }, null, 8, ["modelValue"])
        ]),
        _createElementVNode("div", _hoisted_10, [
          _createVNode(_component_v_text_field, {
            modelValue: config.retry_count,
            "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.retry_count) = $event)),
            modelModifiers: { number: true },
            label: "重试次数",
            type: "number",
            min: "1",
            variant: "outlined",
            density: "comfortable",
            "hide-details": ""
          }, null, 8, ["modelValue"])
        ])
      ])
    ]),
    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(siteList), (site) => {
      return (_openBlock(), _createElementBlock("section", {
        key: site.key,
        class: "ck-panel ck-sec"
      }, [
        _createElementVNode("div", _hoisted_11, [
          _createElementVNode("span", _hoisted_12, _toDisplayString(BADGE[site.key] || '站'), 1),
          _createElementVNode("span", _hoisted_13, _toDisplayString(site.title), 1),
          _createElementVNode("span", _hoisted_14, _toDisplayString(site.mode), 1),
          (config.sites[site.key].enabled)
            ? (_openBlock(), _createElementBlock("span", _hoisted_15, "已启用"))
            : _createCommentVNode("", true)
        ]),
        _createElementVNode("div", _hoisted_16, [
          _createElementVNode("div", _hoisted_17, [
            _createVNode(_component_v_switch, {
              modelValue: config.sites[site.key].enabled,
              "onUpdate:modelValue": $event => ((config.sites[site.key].enabled) = $event),
              color: SEAL,
              label: "启用站点",
              inset: "",
              "hide-details": "",
              density: "comfortable"
            }, null, 8, ["modelValue", "onUpdate:modelValue"])
          ]),
          _createElementVNode("div", _hoisted_18, [
            _createVNode(_component_v_switch, {
              modelValue: config.sites[site.key].use_proxy,
              "onUpdate:modelValue": $event => ((config.sites[site.key].use_proxy) = $event),
              color: SEAL,
              label: "使用代理",
              inset: "",
              "hide-details": "",
              density: "comfortable"
            }, null, 8, ["modelValue", "onUpdate:modelValue"])
          ]),
          (site.key === 'flzt' || site.key === 'ypojie')
            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                _createElementVNode("div", _hoisted_19, [
                  _createVNode(_component_v_text_field, {
                    modelValue: config.sites[site.key].email,
                    "onUpdate:modelValue": $event => ((config.sites[site.key].email) = $event),
                    label: site.key === 'flzt' ? '邮箱' : '账号',
                    variant: "outlined",
                    density: "comfortable",
                    autocomplete: "off",
                    "hide-details": ""
                  }, null, 8, ["modelValue", "onUpdate:modelValue", "label"])
                ]),
                _createElementVNode("div", _hoisted_20, [
                  _createVNode(_component_v_text_field, {
                    modelValue: config.sites[site.key].password,
                    "onUpdate:modelValue": $event => ((config.sites[site.key].password) = $event),
                    label: "密码",
                    type: "password",
                    variant: "outlined",
                    density: "comfortable",
                    autocomplete: "new-password",
                    "hide-details": ""
                  }, null, 8, ["modelValue", "onUpdate:modelValue"])
                ])
              ], 64))
            : (site.key === 'right_forum')
              ? (_openBlock(), _createElementBlock("div", _hoisted_21, [
                  _createVNode(_component_v_textarea, {
                    modelValue: config.sites[site.key].cookie,
                    "onUpdate:modelValue": $event => ((config.sites[site.key].cookie) = $event),
                    label: "Cookie",
                    variant: "outlined",
                    rows: "3",
                    "no-resize": "",
                    "auto-grow": "",
                    density: "comfortable",
                    hint: "从浏览器复制登录后的完整 Cookie",
                    "persistent-hint": ""
                  }, null, 8, ["modelValue", "onUpdate:modelValue"])
                ]))
              : _createCommentVNode("", true)
        ])
      ]))
    }), 128)),
    _createElementVNode("div", _hoisted_22, [
      _createElementVNode("button", {
        class: "ck-btn",
        onClick: _cache[7] || (_cache[7] = $event => (applyConfig(props.initialConfig)))
      }, [...(_cache[13] || (_cache[13] = [
        _createElementVNode("svg", {
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: "currentColor",
          "stroke-width": "2",
          "stroke-linecap": "round",
          "stroke-linejoin": "round",
          width: "16",
          height: "16"
        }, [
          _createElementVNode("path", { d: "M3 12a9 9 0 1 0 3-6.7L3 8" }),
          _createElementVNode("path", { d: "M3 3v5h5" })
        ], -1),
        _createTextVNode(" 重置 ", -1)
      ]))]),
      _createElementVNode("button", {
        class: "ck-btn ck-btn--primary",
        disabled: __props.saving,
        onClick: saveConfig
      }, [
        (__props.saving)
          ? (_openBlock(), _createElementBlock("span", _hoisted_24))
          : (_openBlock(), _createElementBlock("svg", _hoisted_25, [...(_cache[14] || (_cache[14] = [
              _createElementVNode("path", { d: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" }, null, -1),
              _createElementVNode("path", { d: "M17 21v-8H7v8M7 3v5h8" }, null, -1)
            ]))])),
        _cache[15] || (_cache[15] = _createTextVNode(" 保存配置 ", -1))
      ], 8, _hoisted_23)
    ])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-e44c0256"]]);

export { Config as default };
