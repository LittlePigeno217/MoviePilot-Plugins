import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginRequest } from './_plugin-vue_export-helper-22e9664a.js';

const HistoryTable_vue_vue_type_style_index_0_scoped_73f57a34_lang = '';

const {createElementVNode:_createElementVNode$1,resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1} = await importShared('vue');


const _hoisted_1$1 = { class: "history-table" };
const _hoisted_2$1 = { class: "history-head" };

const {ref: ref$1,onMounted} = await importShared('vue');


const _sfc_main$1 = {
  __name: 'HistoryTable',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['toast'],
  setup(__props, { expose: __expose, emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = ref$1(false);
const items = ref$1([]);

const headers = [
  { title: '时间', key: 'time' },
  { title: '新增', key: 'added' },
  { title: '更新', key: 'updated' },
  { title: '跳过', key: 'skipped' },
  { title: '错误', key: 'errors' },
  { title: '耗时(ms)', key: 'duration_ms' },
  { title: '消息', key: 'message' },
];

async function load() {
  loading.value = true;
  try {
    const result = await pluginRequest(props.api, '/history', { method: 'GET' });
    if (!result?.success) throw new Error(result?.message || '获取历史失败')
    items.value = result.data?.items || [];
  } catch (error) {
    emit('toast', error?.message || '获取历史失败', 'error');
  } finally {
    loading.value = false;
  }
}

__expose({ load });

onMounted(load);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_data_table = _resolveComponent$1("v-data-table");

  return (_openBlock$1(), _createElementBlock$1("section", _hoisted_1$1, [
    _createElementVNode$1("div", _hoisted_2$1, [
      _cache[0] || (_cache[0] = _createElementVNode$1("div", { class: "section-title" }, "同步历史", -1)),
      _createVNode$1(_component_v_btn, {
        icon: "mdi-refresh",
        size: "small",
        variant: "text",
        loading: loading.value,
        onClick: load
      }, null, 8, ["loading"])
    ]),
    _createVNode$1(_component_v_data_table, {
      headers: headers,
      items: items.value,
      loading: loading.value,
      density: "compact",
      "items-per-page": "10",
      "no-data-text": "暂无同步记录"
    }, null, 8, ["items", "loading"])
  ]))
}
}

};
const HistoryTable = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-73f57a34"]]);

const Page_vue_vue_type_style_index_0_scoped_fbf4e56f_lang = '';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "p115-page" };
const _hoisted_2 = { class: "page-head" };
const _hoisted_3 = { class: "page-actions" };

const {reactive,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['switch', 'close', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const snackbar = reactive({ show: false, text: '', color: 'info' });

function toast(message, type = 'info') {
  snackbar.text = message;
  snackbar.color = type === 'error' ? 'error' : type === 'success' ? 'success' : 'info';
  snackbar.show = true;
}

const syncing = ref(false);
const historyRef = ref(null);

async function triggerSync() {
  syncing.value = true;
  try {
    const result = await pluginRequest(props.api, '/sync', { method: 'POST' });
    if (!result?.success) throw new Error(result?.message || '触发同步失败')
    toast(result?.message || '同步已在后台开始', 'success');
    setTimeout(() => historyRef.value?.load?.(), 1500);
  } catch (error) {
    toast(error?.message || '触发同步失败', 'error');
  } finally {
    syncing.value = false;
  }
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[4] || (_cache[4] = _createElementVNode("div", { class: "section-title" }, "115 STRM 助手", -1)),
      _createElementVNode("div", _hoisted_3, [
        _createVNode(_component_v_btn, {
          color: "#167A5B",
          variant: "flat",
          loading: syncing.value,
          onClick: triggerSync
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-sync",
              class: "mr-1"
            }),
            _cache[2] || (_cache[2] = _createTextVNode("立即同步 ", -1))
          ]),
          _: 1
        }, 8, ["loading"]),
        _createVNode(_component_v_btn, {
          variant: "text",
          onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-cog-outline",
              class: "mr-1"
            }),
            _cache[3] || (_cache[3] = _createTextVNode("配置 ", -1))
          ]),
          _: 1
        })
      ])
    ]),
    _createVNode(HistoryTable, {
      ref_key: "historyRef",
      ref: historyRef,
      api: __props.api,
      onToast: toast
    }, null, 8, ["api"]),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((snackbar.show) = $event)),
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-fbf4e56f"]]);

export { Page as default };
