import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginRequest } from './_plugin-vue_export-helper-59eae27f.js';
import Config from './__federation_expose_Config-a5b5128f.js';
import Page from './__federation_expose_Page-d1c49f1f.js';

const AppPage_vue_vue_type_style_index_0_scoped_0669aaf5_lang = '';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "p115-app" };

const {reactive,ref,onMounted} = await importShared('vue');


const _sfc_main = {
  __name: 'AppPage',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
},
  setup(__props) {

const props = __props;

const snackbar = reactive({ show: false, text: '', color: 'info' });
const tab = ref('data');
const initialConfig = ref({});
const saving = ref(false);

function toast(message, type = 'info') {
  snackbar.text = message;
  snackbar.color = type === 'error' ? 'error' : type === 'success' ? 'success' : 'info';
  snackbar.show = true;
}

async function loadConfig() {
  try {
    const result = await pluginRequest(props.api, '/config', { method: 'GET' });
    if (result?.success) initialConfig.value = result.data || {};
  } catch (error) {
    toast(error?.message || '加载配置失败', 'error');
  }
}

async function onSave(config) {
  saving.value = true;
  try {
    const result = await pluginRequest(props.api, '/config', { method: 'POST', body: config });
    if (!result?.success) throw new Error(result?.message || '保存失败')
    toast('配置已保存', 'success');
    initialConfig.value = { ...config };
  } catch (error) {
    toast(error?.message || '保存失败', 'error');
  } finally {
    saving.value = false;
  }
}

onMounted(loadConfig);

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_tab = _resolveComponent("v-tab");
  const _component_v_tabs = _resolveComponent("v-tabs");
  const _component_v_window_item = _resolveComponent("v-window-item");
  const _component_v_window = _resolveComponent("v-window");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_tabs, {
      modelValue: tab.value,
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((tab).value = $event)),
      color: "#167A5B",
      density: "comfortable"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_tab, { value: "data" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-view-dashboard-outline",
              class: "mr-1"
            }),
            _cache[6] || (_cache[6] = _createTextVNode("数据", -1))
          ]),
          _: 1
        }),
        _createVNode(_component_v_tab, { value: "config" }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-cog-outline",
              class: "mr-1"
            }),
            _cache[7] || (_cache[7] = _createTextVNode("配置", -1))
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_window, {
      modelValue: tab.value,
      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((tab).value = $event))
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_window_item, { value: "data" }, {
          default: _withCtx(() => [
            _createVNode(Page, {
              api: __props.api,
              onSwitch: _cache[1] || (_cache[1] = $event => (tab.value = 'config'))
            }, null, 8, ["api"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_window_item, { value: "config" }, {
          default: _withCtx(() => [
            _createVNode(Config, {
              api: __props.api,
              "initial-config": initialConfig.value,
              saving: saving.value,
              onSave: onSave,
              onSwitch: _cache[2] || (_cache[2] = $event => (tab.value = 'data')),
              onClose: _cache[3] || (_cache[3] = $event => (tab.value = 'data'))
            }, null, 8, ["api", "initial-config", "saving"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((snackbar.show) = $event)),
      color: snackbar.color,
      timeout: "3000",
      location: "top"
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
const AppPage = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-0669aaf5"]]);

export { AppPage as default };
