import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginGet, a as pluginPost } from './_plugin-vue_export-helper-8a223dfe.js';

const Page_vue_vue_type_style_index_0_scoped_0bb0f762_lang = '';

const Page_vue_vue_type_style_index_1_scoped_0bb0f762_lang = '';

const {createElementVNode:_createElementVNode,normalizeClass:_normalizeClass,resolveComponent:_resolveComponent,mergeProps:_mergeProps,createVNode:_createVNode,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "station-page" };
const _hoisted_2 = { class: "page-head" };
const _hoisted_3 = {
  class: "route-line",
  "aria-label": "运行链路"
};
const _hoisted_4 = { class: "page-tools" };
const _hoisted_5 = {
  class: "state-ruler",
  "aria-label": "当前状态"
};
const _hoisted_6 = {
  class: "command-deck",
  "aria-label": "执行任务"
};
const _hoisted_7 = ["disabled"];
const _hoisted_8 = ["disabled"];
const _hoisted_9 = ["disabled"];
const _hoisted_10 = ["disabled"];
const _hoisted_11 = { class: "ledger" };
const _hoisted_12 = { class: "ledger-head" };
const _hoisted_13 = {
  class: "ledger-table",
  role: "table"
};
const _hoisted_14 = { class: "mono" };
const _hoisted_15 = { class: "kind" };
const _hoisted_16 = { class: "result" };
const _hoisted_17 = {
  key: 0,
  class: "ledger-empty"
};

const {computed,onMounted,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: { api: { type: [Object, Function], default: null }, show_switch: { type: Boolean, default: false } },
  emits: ['switch', 'close', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const status = ref({ running: [], history: [] });
const loading = ref(false);
const message = ref('');
const messageColor = ref('info');
const history = computed(() => status.value.history || []);
const runLabel = computed(() => status.value.running?.length ? status.value.running.join(' / ') : 'IDLE');
const cloudTaskRunning = computed(() => status.value.running?.some(kind => ['strm', 'upload'].includes(kind)));

function tell(text, color = 'info') { message.value = text; messageColor.value = color; }

async function refresh() {
  if (!props.api) return
  loading.value = true;
  try { status.value = await pluginGet(props.api, '/status'); } catch (error) { tell(error?.message || '状态获取失败', 'error'); } finally { loading.value = false; }
}

async function run(path, payload = {}) {
  try {
    const result = await pluginPost(props.api, path, payload);
    tell(result.message || '任务已开始', result.success ? 'success' : 'error');
    await refresh();
    emit('action');
  } catch (error) { tell(error?.message || '执行失败', 'error'); }
}

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_tooltip = _resolveComponent("v-tooltip");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_icon = _resolveComponent("v-icon");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("header", _hoisted_2, [
      _cache[8] || (_cache[8] = _createElementVNode("div", { class: "page-title" }, [
        _createElementVNode("span", null, "115 DRIVE / TASK CONTROL"),
        _createElementVNode("h2", null, "运行台")
      ], -1)),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("b", {
          class: _normalizeClass({ online: status.value.authenticated })
        }, "115", 2),
        _cache[6] || (_cache[6] = _createElementVNode("i", null, null, -1)),
        _createElementVNode("b", {
          class: _normalizeClass({ online: status.value.enabled })
        }, "302", 2),
        _cache[7] || (_cache[7] = _createElementVNode("i", null, null, -1)),
        _createElementVNode("b", {
          class: _normalizeClass({ online: status.value.strm_mappings })
        }, "STRM", 2)
      ]),
      _createElementVNode("div", _hoisted_4, [
        _createVNode(_component_v_tooltip, {
          text: "刷新状态",
          location: "bottom"
        }, {
          activator: _withCtx(({ props: tipProps }) => [
            _createVNode(_component_v_btn, _mergeProps(tipProps, {
              icon: "mdi-refresh",
              variant: "text",
              size: "small",
              loading: loading.value,
              onClick: refresh
            }), null, 16, ["loading"])
          ]),
          _: 1
        }),
        (__props.show_switch)
          ? (_openBlock(), _createBlock(_component_v_tooltip, {
              key: 0,
              text: "配置",
              location: "bottom"
            }, {
              activator: _withCtx(({ props: tipProps }) => [
                _createVNode(_component_v_btn, _mergeProps(tipProps, {
                  icon: "mdi-tune-variant",
                  variant: "text",
                  size: "small",
                  onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
                }), null, 16)
              ]),
              _: 1
            }))
          : _createCommentVNode("", true),
        _createVNode(_component_v_tooltip, {
          text: "关闭",
          location: "bottom"
        }, {
          activator: _withCtx(({ props: tipProps }) => [
            _createVNode(_component_v_btn, _mergeProps(tipProps, {
              icon: "mdi-close",
              variant: "text",
              size: "small",
              onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
            }), null, 16)
          ]),
          _: 1
        })
      ])
    ]),
    (message.value)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
          type: messageColor.value,
          density: "compact",
          variant: "tonal",
          class: "page-alert"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(message.value), 1)
          ]),
          _: 1
        }, 8, ["type"]))
      : _createCommentVNode("", true),
    _createElementVNode("section", _hoisted_5, [
      _createElementVNode("div", null, [
        _cache[9] || (_cache[9] = _createElementVNode("span", null, "授权", -1)),
        _createElementVNode("strong", {
          class: _normalizeClass(status.value.authenticated ? 'ok' : '')
        }, _toDisplayString(status.value.authenticated ? '已连接' : '未登录'), 3)
      ]),
      _createElementVNode("div", null, [
        _cache[10] || (_cache[10] = _createElementVNode("span", null, "STRM 映射", -1)),
        _createElementVNode("strong", null, _toDisplayString(status.value.strm_mappings || 0), 1)
      ]),
      _createElementVNode("div", null, [
        _cache[11] || (_cache[11] = _createElementVNode("span", null, "上传映射", -1)),
        _createElementVNode("strong", null, _toDisplayString(status.value.upload_mappings || 0), 1)
      ]),
      _createElementVNode("div", null, [
        _cache[12] || (_cache[12] = _createElementVNode("span", null, "生活事件", -1)),
        _createElementVNode("strong", {
          class: _normalizeClass(status.value.life_monitor_running ? 'ok' : '')
        }, _toDisplayString(status.value.life_monitor_running ? '监控中' : (status.value.life_monitor_enabled ? '等待启动' : '未启用')), 3)
      ]),
      _createElementVNode("div", null, [
        _cache[13] || (_cache[13] = _createElementVNode("span", null, "执行队列", -1)),
        _createElementVNode("strong", {
          class: _normalizeClass(["mono", { running: status.value.running?.length }])
        }, _toDisplayString(runLabel.value), 3)
      ])
    ]),
    _createElementVNode("section", _hoisted_6, [
      _createElementVNode("button", {
        class: "command command--strm",
        disabled: cloudTaskRunning.value,
        onClick: _cache[2] || (_cache[2] = $event => (run('/strm/sync')))
      }, [
        _createVNode(_component_v_icon, {
          icon: "mdi-file-link-outline",
          size: "23"
        }),
        _cache[14] || (_cache[14] = _createElementVNode("span", null, [
          _createElementVNode("b", null, "生成 STRM"),
          _createElementVNode("small", null, "目录同步")
        ], -1)),
        _createVNode(_component_v_icon, {
          icon: "mdi-arrow-up-right",
          size: "17"
        })
      ], 8, _hoisted_7),
      _createElementVNode("button", {
        class: "command",
        disabled: cloudTaskRunning.value,
        onClick: _cache[3] || (_cache[3] = $event => (run('/upload', { incremental: false })))
      }, [
        _createVNode(_component_v_icon, {
          icon: "mdi-upload-outline",
          size: "23"
        }),
        _cache[15] || (_cache[15] = _createElementVNode("span", null, [
          _createElementVNode("b", null, "全量上传"),
          _createElementVNode("small", null, "重新扫描")
        ], -1)),
        _createVNode(_component_v_icon, {
          icon: "mdi-arrow-up-right",
          size: "17"
        })
      ], 8, _hoisted_8),
      _createElementVNode("button", {
        class: "command",
        disabled: cloudTaskRunning.value,
        onClick: _cache[4] || (_cache[4] = $event => (run('/upload', { incremental: true })))
      }, [
        _createVNode(_component_v_icon, {
          icon: "mdi-upload-network-outline",
          size: "23"
        }),
        _cache[16] || (_cache[16] = _createElementVNode("span", null, [
          _createElementVNode("b", null, "增量上传"),
          _createElementVNode("small", null, "仅变更项")
        ], -1)),
        _createVNode(_component_v_icon, {
          icon: "mdi-arrow-up-right",
          size: "17"
        })
      ], 8, _hoisted_9),
      _createElementVNode("button", {
        class: "command command--checkin",
        disabled: cloudTaskRunning.value,
        onClick: _cache[5] || (_cache[5] = $event => (run('/checkin')))
      }, [
        _createVNode(_component_v_icon, {
          icon: "mdi-calendar-check-outline",
          size: "23"
        }),
        _cache[17] || (_cache[17] = _createElementVNode("span", null, [
          _createElementVNode("b", null, "立即签到"),
          _createElementVNode("small", null, "115 积分")
        ], -1)),
        _createVNode(_component_v_icon, {
          icon: "mdi-arrow-up-right",
          size: "17"
        })
      ], 8, _hoisted_10)
    ]),
    _createElementVNode("section", _hoisted_11, [
      _createElementVNode("div", _hoisted_12, [
        _cache[18] || (_cache[18] = _createElementVNode("div", null, [
          _createElementVNode("span", null, "EXECUTION LOG"),
          _createElementVNode("h3", null, "最近记录")
        ], -1)),
        _createElementVNode("span", null, _toDisplayString(history.value.length) + " 条", 1)
      ]),
      _createElementVNode("div", _hoisted_13, [
        _cache[20] || (_cache[20] = _createElementVNode("div", {
          class: "ledger-row ledger-label",
          role: "row"
        }, [
          _createElementVNode("span", null, "时间"),
          _createElementVNode("span", null, "类型"),
          _createElementVNode("span", null, "结果")
        ], -1)),
        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(history.value, (item, index) => {
          return (_openBlock(), _createElementBlock("div", {
            key: `${item.time}-${index}`,
            class: "ledger-row",
            role: "row"
          }, [
            _createElementVNode("time", _hoisted_14, _toDisplayString(item.time), 1),
            _createElementVNode("span", _hoisted_15, [
              _cache[19] || (_cache[19] = _createElementVNode("i", null, null, -1)),
              _createTextVNode(_toDisplayString(item.kind), 1)
            ]),
            _createElementVNode("span", _hoisted_16, _toDisplayString(item.message || `上传 ${item.uploaded || 0}，秒传 ${item.instant || 0}，删除 ${item.deleted || 0}，STRM ${item.added || 0}`), 1)
          ]))
        }), 128)),
        (!history.value.length)
          ? (_openBlock(), _createElementBlock("div", _hoisted_17, "暂无执行记录"))
          : _createCommentVNode("", true)
      ])
    ])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-0bb0f762"]]);

export { Page as default };
