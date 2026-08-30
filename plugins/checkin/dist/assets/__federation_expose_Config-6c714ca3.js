import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, n as normalizeConfig, u as useHostNotice, A as AppBar, S as SITE_META, p as pluginGet, v as validateConfig, c as clone } from './kit-34d2ba60.js';

const Config_vue_vue_type_style_index_0_scoped_e7493655_lang = '';

const {createVNode:_createVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,resolveComponent:_resolveComponent,unref:_unref,renderList:_renderList,Fragment:_Fragment,createBlock:_createBlock,withCtx:_withCtx} = await importShared('vue');


const _hoisted_1 = { class: "ck cfg" };
const _hoisted_2 = { class: "ck-sheet" };
const _hoisted_3 = { class: "cfg__switches" };
const _hoisted_4 = { class: "cfg__fields" };
const _hoisted_5 = { class: "ck-sheet__head" };
const _hoisted_6 = { class: "ck-title cfg__site-title" };
const _hoisted_7 = {
  class: "cfg__badge ck-mono",
  "aria-hidden": "true"
};
const _hoisted_8 = { class: "ck-chip" };
const _hoisted_9 = {
  key: 0,
  class: "ck-chip ck-chip--warn"
};
const _hoisted_10 = { class: "cfg__fields" };
const _hoisted_11 = { class: "cfg__foot" };
const _hoisted_12 = { class: "cfg__foot-acts" };

const {computed,inject,reactive,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: [Object, Function], default: null },
  saving: { type: Boolean, default: false },
  lastSavedAt: { type: Number, default: 0 },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

// 自用签到 · 设置页。视觉与台账页同一套语言，校验逻辑不变：
// 保存前跑一遍 validateConfig，通过后交给宿主写入配置。
const props = __props;
const emit = __emit;

const config = reactive(normalizeConfig());
const submitted = ref(false);
const local = reactive({ text: '', kind: 'info' });
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text;
  local.kind = kind;
});

const siteList = Object.values(SITE_META);

// 每个站点是不是「开了但没填」——设置页唯一需要提醒的事
function pending(key) {
  const site = config.sites[key];
  if (!site?.enabled) return false
  if (key === 'right_forum') return !String(site.cookie || '').trim()
  return !site.email || !site.password
}

const openCount = computed(() => siteList.filter(site => config.sites[site.key]?.enabled).length);
const pendingCount = computed(() => siteList.filter(site => pending(site.key)).length);

const barState = computed(() => {
  if (!openCount.value) return '没有启用站点'
  if (pendingCount.value) return `${pendingCount.value} 个站点待填写`
  return `${openCount.value} 个站点就绪`
});
const barTone = computed(() => {
  if (!openCount.value) return 'idle'
  return pendingCount.value ? 'warn' : 'on'
});

function apply(value = {}) {
  Object.assign(config, normalizeConfig(value));
}

async function reload() {
  if (!props.api) {
    apply(props.initialConfig);
    return
  }
  try {
    apply(await pluginGet(props.api, '/config'));
    notice.info('已读取当前配置');
  } catch (error) {
    notice.error(error?.message || '配置读取失败');
  }
}

function save() {
  const errors = validateConfig(config);
  if (errors.length) {
    submitted.value = false;
    notice.error(errors.join('；'));
    return
  }
  submitted.value = true;
  emit('save', clone(config));
}

watch(() => props.initialConfig, apply, { immediate: true, deep: true });
watch(() => props.lastSavedAt, value => {
  if (!value || !submitted.value) return
  submitted.value = false;
  notice.success('配置已保存');
});

return (_ctx, _cache) => {
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_btn = _resolveComponent("v-btn");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(AppBar, {
      view: "设置",
      state: barState.value,
      tone: barTone.value,
      "show-refresh": "",
      onRefresh: reload,
      onSwitch: _cache[0] || (_cache[0] = $event => (emit('switch'))),
      onClose: _cache[1] || (_cache[1] = $event => (emit('close')))
    }, null, 8, ["state", "tone"]),
    (local.text)
      ? (_openBlock(), _createElementBlock("button", {
          key: 0,
          type: "button",
          class: _normalizeClass(["cfg__local", `cfg__local--${local.kind}`]),
          onClick: _cache[2] || (_cache[2] = $event => (local.text = ''))
        }, [
          _createTextVNode(_toDisplayString(local.text) + " ", 1),
          _cache[8] || (_cache[8] = _createElementVNode("span", { class: "cfg__local-x" }, "知道了", -1))
        ], 2))
      : _createCommentVNode("", true),
    _createElementVNode("section", _hoisted_2, [
      _cache[9] || (_cache[9] = _createElementVNode("div", { class: "ck-sheet__head" }, [
        _createElementVNode("h3", { class: "ck-title" }, "执行方式"),
        _createElementVNode("p", { class: "ck-hint" }, "插件关掉时定时任务不会注册，手动签到也不会执行。")
      ], -1)),
      _createElementVNode("div", _hoisted_3, [
        _createVNode(_component_v_switch, {
          modelValue: config.enabled,
          "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.enabled) = $event)),
          color: "primary",
          density: "compact",
          "hide-details": "",
          label: "启用插件"
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_switch, {
          modelValue: config.notify,
          "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.notify) = $event)),
          color: "primary",
          density: "compact",
          "hide-details": "",
          label: "执行后发送通知"
        }, null, 8, ["modelValue"])
      ]),
      _createElementVNode("div", _hoisted_4, [
        _createVNode(_component_v_text_field, {
          modelValue: config.cron,
          "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.cron) = $event)),
          label: "执行时间",
          variant: "outlined",
          density: "compact",
          placeholder: "10 8 * * *",
          hint: "cron 表达式，10 8 * * * 是每天 08:10",
          "persistent-hint": ""
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_text_field, {
          modelValue: config.timeout,
          "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.timeout) = $event)),
          modelModifiers: { number: true },
          label: "单次请求超时（秒）",
          type: "number",
          min: "5",
          variant: "outlined",
          density: "compact",
          "hide-details": ""
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_text_field, {
          modelValue: config.retry_count,
          "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.retry_count) = $event)),
          modelModifiers: { number: true },
          label: "失败重试次数",
          type: "number",
          min: "1",
          variant: "outlined",
          density: "compact",
          "hide-details": ""
        }, null, 8, ["modelValue"])
      ])
    ]),
    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(siteList), (site) => {
      return (_openBlock(), _createElementBlock("section", {
        key: site.key,
        class: "ck-sheet"
      }, [
        _createElementVNode("div", _hoisted_5, [
          _createElementVNode("h3", _hoisted_6, [
            _createElementVNode("span", _hoisted_7, _toDisplayString(site.badge), 1),
            _createTextVNode(" " + _toDisplayString(site.title) + " ", 1),
            _createElementVNode("span", _hoisted_8, _toDisplayString(site.mode), 1),
            (pending(site.key))
              ? (_openBlock(), _createElementBlock("span", _hoisted_9, "待填写"))
              : _createCommentVNode("", true)
          ]),
          _createVNode(_component_v_switch, {
            modelValue: config.sites[site.key].enabled,
            "onUpdate:modelValue": $event => ((config.sites[site.key].enabled) = $event),
            color: "primary",
            density: "compact",
            "hide-details": "",
            label: config.sites[site.key].enabled ? '已启用' : '已关闭'
          }, null, 8, ["modelValue", "onUpdate:modelValue", "label"])
        ]),
        _createElementVNode("div", _hoisted_10, [
          (site.key === 'right_forum')
            ? (_openBlock(), _createBlock(_component_v_textarea, {
                key: 0,
                modelValue: config.sites[site.key].cookie,
                "onUpdate:modelValue": $event => ((config.sites[site.key].cookie) = $event),
                class: "cfg__wide",
                label: "Cookie",
                variant: "outlined",
                density: "compact",
                rows: "3",
                "auto-grow": "",
                "no-resize": "",
                hint: "从浏览器复制登录后的完整 Cookie，需要包含 auth 或 saltkey",
                "persistent-hint": ""
              }, null, 8, ["modelValue", "onUpdate:modelValue"]))
            : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                _createVNode(_component_v_text_field, {
                  modelValue: config.sites[site.key].email,
                  "onUpdate:modelValue": $event => ((config.sites[site.key].email) = $event),
                  label: site.key === 'flzt' ? '登录邮箱' : '登录账号',
                  variant: "outlined",
                  density: "compact",
                  autocomplete: "off",
                  "hide-details": ""
                }, null, 8, ["modelValue", "onUpdate:modelValue", "label"]),
                _createVNode(_component_v_text_field, {
                  modelValue: config.sites[site.key].password,
                  "onUpdate:modelValue": $event => ((config.sites[site.key].password) = $event),
                  label: "密码",
                  type: "password",
                  variant: "outlined",
                  density: "compact",
                  autocomplete: "new-password",
                  "hide-details": ""
                }, null, 8, ["modelValue", "onUpdate:modelValue"])
              ], 64)),
          _createVNode(_component_v_switch, {
            modelValue: config.sites[site.key].use_proxy,
            "onUpdate:modelValue": $event => ((config.sites[site.key].use_proxy) = $event),
            color: "primary",
            density: "compact",
            "hide-details": "",
            label: "通过代理访问"
          }, null, 8, ["modelValue", "onUpdate:modelValue"])
        ])
      ]))
    }), 128)),
    _createElementVNode("footer", _hoisted_11, [
      _cache[12] || (_cache[12] = _createElementVNode("span", { class: "cfg__foot-note ck-muted" }, "保存后立即生效，无需重启 MoviePilot。", -1)),
      _createElementVNode("span", _hoisted_12, [
        _createVNode(_component_v_btn, {
          variant: "text",
          size: "small",
          disabled: __props.saving,
          onClick: reload
        }, {
          default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
            _createTextVNode("放弃改动", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"]),
        _createVNode(_component_v_btn, {
          color: "primary",
          variant: "flat",
          size: "small",
          loading: __props.saving,
          onClick: save
        }, {
          default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
            _createTextVNode("保存配置", -1)
          ]))]),
          _: 1
        }, 8, ["loading"])
      ])
    ])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-e7493655"]]);

export { Config as default };
