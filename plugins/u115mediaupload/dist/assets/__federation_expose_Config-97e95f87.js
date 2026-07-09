import { importShared } from './__federation_fn_import-054b33c3.js';
import { A as AuthPanel, P as PathMappingEditor } from './PathMappingEditor-3f05e3a1.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-75e59c87.js';

const Config_vue_vue_type_style_index_0_scoped_aad0f5d2_lang = '';

const {createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "u115-config" };
const _hoisted_2 = { class: "config-head" };
const _hoisted_3 = { class: "head-actions" };
const _hoisted_4 = { class: "config-grid" };
const _hoisted_5 = { class: "panel" };
const _hoisted_6 = { class: "panel" };
const _hoisted_7 = { class: "panel wide" };
const _hoisted_8 = { class: "panel" };
const _hoisted_9 = { class: "panel" };

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
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const defaultConfig = {
  enabled: false,
  auth_mode: 'cookie',
  cookie: '',
  tokens: {},
  path_mappings: [],
  media_extensions: ['.mkv', '.mp4', '.avi', '.mov', '.ts', '.iso', '.m2ts', '.rmvb', '.wmv'],
  sidecar_extensions: ['.nfo', '.jpg', '.jpeg', '.png', '.webp', '.srt', '.ass', '.ssa', '.sup'],
  upload_existing_sidecars: true,
  scrape_before_upload: false,
  scrape_overwrite: false,
  event_incremental: true,
  cron: '',
  concurrency: 1,
};

const config = reactive({ ...defaultConfig });
const mediaExtensionsText = ref('');
const sidecarExtensionsText = ref('');
const snackbar = reactive({ show: false, text: '', color: 'success' });

function extListToText(values) {
  return (values || []).join('\n')
}

function textToExtList(value) {
  return String(value || '')
    .split(/[\n,，\s]+/)
    .map(item => item.trim().toLowerCase())
    .filter(Boolean)
    .map(item => (item.startsWith('.') ? item : `.${item}`))
}

function applyConfig(value) {
  Object.assign(config, defaultConfig, value || {});
  mediaExtensionsText.value = extListToText(config.media_extensions);
  sidecarExtensionsText.value = extListToText(config.sidecar_extensions);
}

function saveConfig() {
  emit('save', {
    ...config,
    media_extensions: textToExtList(mediaExtensionsText.value),
    sidecar_extensions: textToExtList(sidecarExtensionsText.value),
  });
}

function toast(text, color = 'success') {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

watch(
  () => props.initialConfig,
  (value) => applyConfig(value),
  { deep: true, immediate: true }
);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("header", _hoisted_2, [
      _cache[15] || (_cache[15] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "title" }, "115媒体上传"),
        _createElementVNode("div", { class: "subtitle" }, "配置授权、路径、刮削和增量触发")
      ], -1)),
      _createElementVNode("div", _hoisted_3, [
        _createVNode(_component_v_btn, {
          color: "#245B7A",
          variant: "tonal",
          onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
        }, {
          default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
            _createTextVNode("状态页", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_v_btn, {
          color: "#167A5B",
          variant: "flat",
          onClick: saveConfig
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-content-save-outline",
              class: "mr-1"
            }),
            _cache[14] || (_cache[14] = _createTextVNode("保存 ", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_v_btn, {
          icon: "mdi-close",
          variant: "text",
          onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
        })
      ])
    ]),
    _createElementVNode("div", _hoisted_4, [
      _createElementVNode("section", _hoisted_5, [
        _cache[16] || (_cache[16] = _createElementVNode("div", { class: "section-title" }, "基础", -1)),
        _createVNode(_component_v_switch, {
          modelValue: config.enabled,
          "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.enabled) = $event)),
          color: "#167A5B",
          label: "启用插件",
          inset: ""
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_switch, {
          modelValue: config.event_incremental,
          "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.event_incremental) = $event)),
          color: "#167A5B",
          label: "整理完成后自动增量",
          inset: ""
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_text_field, {
          modelValue: config.cron,
          "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.cron) = $event)),
          label: "定时增量 Cron",
          variant: "outlined",
          density: "comfortable",
          hint: "留空表示不启用定时增量",
          "persistent-hint": ""
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_text_field, {
          modelValue: config.concurrency,
          "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.concurrency) = $event)),
          modelModifiers: { number: true },
          label: "并发数",
          variant: "outlined",
          density: "comfortable",
          type: "number",
          min: "1",
          max: "4"
        }, null, 8, ["modelValue"])
      ]),
      _createElementVNode("section", _hoisted_6, [
        _createVNode(AuthPanel, {
          api: __props.api,
          config: config,
          "onUpdate:config": applyConfig,
          onToast: toast
        }, null, 8, ["api", "config"])
      ]),
      _createElementVNode("section", _hoisted_7, [
        _createVNode(PathMappingEditor, {
          mappings: config.path_mappings,
          "onUpdate:mappings": _cache[6] || (_cache[6] = $event => ((config.path_mappings) = $event))
        }, null, 8, ["mappings"])
      ]),
      _createElementVNode("section", _hoisted_8, [
        _cache[17] || (_cache[17] = _createElementVNode("div", { class: "section-title" }, "刮削文件", -1)),
        _createVNode(_component_v_switch, {
          modelValue: config.upload_existing_sidecars,
          "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.upload_existing_sidecars) = $event)),
          color: "#167A5B",
          label: "上传已有附属文件",
          inset: ""
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_switch, {
          modelValue: config.scrape_before_upload,
          "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.scrape_before_upload) = $event)),
          color: "#167A5B",
          label: "上传前执行刮削",
          inset: ""
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_switch, {
          modelValue: config.scrape_overwrite,
          "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.scrape_overwrite) = $event)),
          color: "#B7791F",
          label: "刮削覆盖已有文件",
          inset: ""
        }, null, 8, ["modelValue"])
      ]),
      _createElementVNode("section", _hoisted_9, [
        _cache[18] || (_cache[18] = _createElementVNode("div", { class: "section-title" }, "扩展名", -1)),
        _createVNode(_component_v_textarea, {
          modelValue: mediaExtensionsText.value,
          "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((mediaExtensionsText).value = $event)),
          label: "媒体扩展名",
          variant: "outlined",
          rows: "4",
          "auto-grow": ""
        }, null, 8, ["modelValue"]),
        _createVNode(_component_v_textarea, {
          modelValue: sidecarExtensionsText.value,
          "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((sidecarExtensionsText).value = $event)),
          label: "附属文件扩展名",
          variant: "outlined",
          rows: "4",
          "auto-grow": ""
        }, null, 8, ["modelValue"])
      ])
    ]),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((snackbar.show) = $event)),
      color: snackbar.color,
      timeout: "3000"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(snackbar.text), 1)
      ]),
      _: 1
    }, 8, ["modelValue", "color"])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-aad0f5d2"]]);

export { Config as default };
