import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginRequest } from './_plugin-vue_export-helper-75e59c87.js';

const AuthPanel_vue_vue_type_style_index_0_scoped_5ca1a2bc_lang = '';

const {createElementVNode:_createElementVNode$1,resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,createTextVNode:_createTextVNode$1,withCtx:_withCtx$1,openBlock:_openBlock$1,createBlock:_createBlock,createCommentVNode:_createCommentVNode$1,createElementBlock:_createElementBlock$1} = await importShared('vue');


const _hoisted_1$1 = { class: "auth-panel" };
const _hoisted_2$1 = {
  key: 1,
  class: "qrcode-box"
};
const _hoisted_3$1 = { class: "qrcode-actions" };

const {reactive,ref} = await importShared('vue');


const _sfc_main$1 = {
  __name: 'AuthPanel',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
  config: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['update:config', 'toast'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = reactive({ qrcode: false, check: false });
const qrcode = ref('');

function update(key, value) {
  emit('update:config', { ...props.config, [key]: value });
}

async function generateQrcode() {
  loading.qrcode = true;
  try {
    const result = await pluginRequest(props.api, '/qrcode', { method: 'POST' });
    if (!result?.success) throw new Error(result?.message || '生成二维码失败')
    qrcode.value = result?.data?.codeContent || '';
    emit('toast', '二维码内容已生成');
  } catch (error) {
    emit('toast', error?.message || '生成二维码失败', 'error');
  } finally {
    loading.qrcode = false;
  }
}

async function checkLogin() {
  loading.check = true;
  try {
    const result = await pluginRequest(props.api, '/check_login');
    if (!result?.success) throw new Error(result?.message || '登录未完成')
    emit('toast', result?.data?.tip || '登录状态已更新');
  } catch (error) {
    emit('toast', error?.message || '检查登录失败', 'error');
  } finally {
    loading.check = false;
  }
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_btn_toggle = _resolveComponent$1("v-btn-toggle");
  const _component_v_textarea = _resolveComponent$1("v-textarea");

  return (_openBlock$1(), _createElementBlock$1("section", _hoisted_1$1, [
    _cache[7] || (_cache[7] = _createElementVNode$1("div", { class: "section-title" }, "115 授权", -1)),
    _createVNode$1(_component_v_btn_toggle, {
      "model-value": __props.config.auth_mode,
      mandatory: "",
      color: "#167A5B",
      variant: "outlined",
      density: "comfortable",
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => (update('auth_mode', $event)))
    }, {
      default: _withCtx$1(() => [
        _createVNode$1(_component_v_btn, { value: "cookie" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, {
              icon: "mdi-cookie-outline",
              class: "mr-1"
            }),
            _cache[3] || (_cache[3] = _createTextVNode$1("Cookie", -1))
          ]),
          _: 1
        }),
        _createVNode$1(_component_v_btn, { value: "qrcode" }, {
          default: _withCtx$1(() => [
            _createVNode$1(_component_v_icon, {
              icon: "mdi-qrcode-scan",
              class: "mr-1"
            }),
            _cache[4] || (_cache[4] = _createTextVNode$1("扫码", -1))
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["model-value"]),
    (__props.config.auth_mode === 'cookie')
      ? (_openBlock$1(), _createBlock(_component_v_textarea, {
          key: 0,
          "model-value": __props.config.cookie,
          label: "115 Cookie",
          variant: "outlined",
          rows: "4",
          "auto-grow": "",
          "hide-details": "",
          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => (update('cookie', $event)))
        }, null, 8, ["model-value"]))
      : (_openBlock$1(), _createElementBlock$1("div", _hoisted_2$1, [
          _createElementVNode$1("div", _hoisted_3$1, [
            _createVNode$1(_component_v_btn, {
              color: "#167A5B",
              variant: "flat",
              loading: loading.qrcode,
              onClick: generateQrcode
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_icon, {
                  icon: "mdi-qrcode-plus",
                  class: "mr-1"
                }),
                _cache[5] || (_cache[5] = _createTextVNode$1("生成 ", -1))
              ]),
              _: 1
            }, 8, ["loading"]),
            _createVNode$1(_component_v_btn, {
              color: "#245B7A",
              variant: "tonal",
              loading: loading.check,
              onClick: checkLogin
            }, {
              default: _withCtx$1(() => [
                _createVNode$1(_component_v_icon, {
                  icon: "mdi-check-circle-outline",
                  class: "mr-1"
                }),
                _cache[6] || (_cache[6] = _createTextVNode$1("检查 ", -1))
              ]),
              _: 1
            }, 8, ["loading"])
          ]),
          _createVNode$1(_component_v_textarea, {
            modelValue: qrcode.value,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((qrcode).value = $event)),
            label: "二维码内容",
            variant: "outlined",
            rows: "3",
            "auto-grow": "",
            readonly: "",
            "hide-details": ""
          }, null, 8, ["modelValue"])
        ]))
  ]))
}
}

};
const AuthPanel = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-5ca1a2bc"]]);

const PathMappingEditor_vue_vue_type_style_index_0_scoped_4dfc63e9_lang = '';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "mapping-editor" };
const _hoisted_2 = { class: "mapping-editor__head" };
const _hoisted_3 = {
  key: 0,
  class: "empty-line"
};


const _sfc_main = {
  __name: 'PathMappingEditor',
  props: {
  mappings: {
    type: Array,
    default: () => [],
  },
},
  emits: ['update:mappings'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

function updateMapping(index, key, value) {
  const next = props.mappings.map((item, idx) => (idx === index ? { ...item, [key]: value } : item));
  emit('update:mappings', next);
}

function addMapping() {
  emit('update:mappings', [...props.mappings, { enabled: true, source: '', target: '/' }]);
}

function removeMapping(index) {
  emit('update:mappings', props.mappings.filter((_, idx) => idx !== index));
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_text_field = _resolveComponent("v-text-field");

  return (_openBlock(), _createElementBlock("section", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[1] || (_cache[1] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "section-title" }, "路径映射"),
        _createElementVNode("div", { class: "section-subtitle" }, "本地目录上传到对应 115 目录")
      ], -1)),
      _createVNode(_component_v_btn, {
        color: "#167A5B",
        variant: "flat",
        size: "small",
        onClick: addMapping
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_icon, {
            icon: "mdi-plus",
            class: "mr-1"
          }),
          _cache[0] || (_cache[0] = _createTextVNode("新增 ", -1))
        ]),
        _: 1
      })
    ]),
    (!__props.mappings.length)
      ? (_openBlock(), _createElementBlock("div", _hoisted_3, "暂无路径映射"))
      : _createCommentVNode("", true),
    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.mappings, (mapping, index) => {
      return (_openBlock(), _createElementBlock("div", {
        key: index,
        class: "mapping-row"
      }, [
        _createVNode(_component_v_switch, {
          "model-value": mapping.enabled,
          color: "#167A5B",
          density: "compact",
          "hide-details": "",
          inset: "",
          "onUpdate:modelValue": $event => (updateMapping(index, 'enabled', $event))
        }, null, 8, ["model-value", "onUpdate:modelValue"]),
        _createVNode(_component_v_text_field, {
          "model-value": mapping.source,
          label: "本地目录",
          variant: "outlined",
          density: "compact",
          "hide-details": "",
          "prepend-inner-icon": "mdi-folder-outline",
          "onUpdate:modelValue": $event => (updateMapping(index, 'source', $event))
        }, null, 8, ["model-value", "onUpdate:modelValue"]),
        _createVNode(_component_v_text_field, {
          "model-value": mapping.target,
          label: "115 目录",
          variant: "outlined",
          density: "compact",
          "hide-details": "",
          "prepend-inner-icon": "mdi-cloud-outline",
          "onUpdate:modelValue": $event => (updateMapping(index, 'target', $event))
        }, null, 8, ["model-value", "onUpdate:modelValue"]),
        _createVNode(_component_v_btn, {
          icon: "mdi-delete-outline",
          variant: "text",
          color: "#B42318",
          onClick: $event => (removeMapping(index))
        }, null, 8, ["onClick"])
      ]))
    }), 128))
  ]))
}
}

};
const PathMappingEditor = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-4dfc63e9"]]);

export { AuthPanel as A, PathMappingEditor as P };
