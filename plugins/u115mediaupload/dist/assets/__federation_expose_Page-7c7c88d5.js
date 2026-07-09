import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginRequest, n as normalizeResponse } from './_plugin-vue_export-helper-75e59c87.js';

const Page_vue_vue_type_style_index_0_scoped_13f08d7d_lang = '';

const {createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "u115-page" };
const _hoisted_2 = { class: "page-head" };
const _hoisted_3 = { class: "page-actions" };
const _hoisted_4 = { class: "summary-value" };
const _hoisted_5 = { class: "summary-value" };
const _hoisted_6 = { class: "stats" };
const _hoisted_7 = { class: "result-box" };

const {computed,onMounted,reactive,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['switch', 'close', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = reactive({ status: false, full: false, incremental: false });
const snackbar = reactive({ show: false, text: '', color: 'success' });
const status = ref({
  phase: 'idle',
  message: '未执行',
  running: false,
  counts: { scanned: 0, planned: 0, reused: 0, uploaded: 0, failed: 0 },
  authorized: false,
  enabled: false,
});

function toast(text, color = 'success') {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

async function loadStatus(showMessage = false) {
  loading.status = true;
  try {
    const result = await pluginRequest(props.api, '/status');
    if (!result?.success) throw new Error(result?.message || '获取状态失败')
    status.value = normalizeResponse(result, status.value);
    if (showMessage) toast('状态已刷新');
  } catch (error) {
    toast(error?.message || '获取状态失败', 'error');
  } finally {
    loading.status = false;
  }
}

async function run(path, flag) {
  loading[flag] = true;
  try {
    const result = await pluginRequest(props.api, path, { method: 'POST' });
    if (!result?.success) throw new Error(result?.message || '执行失败')
    toast(result?.message || '任务已启动');
    await loadStatus();
    emit('action');
  } catch (error) {
    toast(error?.message || '执行失败', 'error');
  } finally {
    loading[flag] = false;
  }
}

async function stopTask() {
  await run('/stop', 'full');
}

const statusColor = computed(() => (status.value.enabled ? '#167A5B' : '#66736D'));

onMounted(() => loadStatus());

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("header", _hoisted_2, [
      _cache[10] || (_cache[10] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "page-title" }, "115媒体上传"),
        _createElementVNode("div", { class: "page-subtitle" }, "快速状态、手动执行和授权概览")
      ], -1)),
      _createElementVNode("div", _hoisted_3, [
        _createVNode(_component_v_btn, {
          color: "#167A5B",
          variant: "flat",
          loading: loading.full,
          disabled: status.value.running,
          onClick: _cache[0] || (_cache[0] = $event => (run('/run_full', 'full')))
        }, {
          default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
            _createTextVNode(" 全量上传 ", -1)
          ]))]),
          _: 1
        }, 8, ["loading", "disabled"]),
        _createVNode(_component_v_btn, {
          color: "#245B7A",
          variant: "flat",
          loading: loading.incremental,
          disabled: status.value.running,
          onClick: _cache[1] || (_cache[1] = $event => (run('/run_incremental', 'incremental')))
        }, {
          default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
            _createTextVNode(" 增量上传 ", -1)
          ]))]),
          _: 1
        }, 8, ["loading", "disabled"]),
        _createVNode(_component_v_btn, {
          color: "#B42318",
          variant: "tonal",
          disabled: !status.value.running,
          onClick: stopTask
        }, {
          default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
            _createTextVNode("停止", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"]),
        _createVNode(_component_v_btn, {
          icon: "mdi-refresh",
          variant: "text",
          loading: loading.status,
          onClick: _cache[2] || (_cache[2] = $event => (loadStatus(true)))
        }, null, 8, ["loading"]),
        _createVNode(_component_v_btn, {
          variant: "text",
          onClick: _cache[3] || (_cache[3] = $event => (emit('switch')))
        }, {
          default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
            _createTextVNode("配置", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_v_btn, {
          icon: "mdi-close",
          variant: "text",
          onClick: _cache[4] || (_cache[4] = $event => (emit('close')))
        })
      ])
    ]),
    _createVNode(_component_v_row, null, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, {
          cols: "12",
          md: "4"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              variant: "outlined",
              class: "panel-card"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, null, {
                  default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
                    _createTextVNode("运行概览", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, { class: "summary-grid" }, {
                  default: _withCtx(() => [
                    _createElementVNode("div", null, [
                      _cache[12] || (_cache[12] = _createElementVNode("div", { class: "summary-label" }, "插件状态", -1)),
                      _createVNode(_component_v_chip, {
                        color: statusColor.value,
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(status.value.enabled ? '已启用' : '未启用'), 1)
                        ]),
                        _: 1
                      }, 8, ["color"])
                    ]),
                    _createElementVNode("div", null, [
                      _cache[13] || (_cache[13] = _createElementVNode("div", { class: "summary-label" }, "授权状态", -1)),
                      _createVNode(_component_v_chip, {
                        color: status.value.authorized ? '#167A5B' : '#B42318',
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(status.value.authorized ? '已授权' : '未授权'), 1)
                        ]),
                        _: 1
                      }, 8, ["color"])
                    ]),
                    _createElementVNode("div", null, [
                      _cache[14] || (_cache[14] = _createElementVNode("div", { class: "summary-label" }, "当前阶段", -1)),
                      _createElementVNode("div", _hoisted_4, _toDisplayString(status.value.phase), 1)
                    ]),
                    _createElementVNode("div", null, [
                      _cache[15] || (_cache[15] = _createElementVNode("div", { class: "summary-label" }, "最近更新", -1)),
                      _createElementVNode("div", _hoisted_5, _toDisplayString(status.value.updated_at || '-'), 1)
                    ])
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
          md: "8"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              variant: "outlined",
              class: "panel-card"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, null, {
                  default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                    _createTextVNode("任务统计", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_6, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(status.value.counts, (item, key) => {
                        return (_openBlock(), _createElementBlock("div", {
                          key: key,
                          class: "stat"
                        }, [
                          _createElementVNode("span", null, _toDisplayString(key), 1),
                          _createElementVNode("strong", null, _toDisplayString(item), 1)
                        ]))
                      }), 128))
                    ])
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
    _createVNode(_component_v_card, {
      variant: "outlined",
      class: "panel-card mt-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, null, {
          default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
            _createTextVNode("最近结果", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            _createElementVNode("pre", _hoisted_7, _toDisplayString(status.value.last_result ? JSON.stringify(status.value.last_result, null, 2) : '暂无任务结果'), 1)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((snackbar.show) = $event)),
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-13f08d7d"]]);

export { Page as default };
