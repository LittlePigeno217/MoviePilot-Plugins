import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginRequest, n as normalizeResponse } from './_plugin-vue_export-helper-75e59c87.js';
import { A as AuthPanel, P as PathMappingEditor } from './PathMappingEditor-a06c3554.js';

const HistoryTable_vue_vue_type_style_index_0_scoped_7d228909_lang = '';

const {createTextVNode:_createTextVNode$2,resolveComponent:_resolveComponent$2,withCtx:_withCtx$2,createVNode:_createVNode$2,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode$2,renderList:_renderList$1,Fragment:_Fragment$1,toDisplayString:_toDisplayString$2} = await importShared('vue');


const _hoisted_1$2 = { class: "history-table" };
const _hoisted_2$2 = {
  key: 0,
  class: "empty-line"
};
const _hoisted_3$2 = {
  key: 1,
  class: "table-wrap"
};
const _hoisted_4$2 = {
  key: 0,
  class: "empty-line"
};
const _hoisted_5$2 = {
  key: 1,
  class: "table-wrap"
};

const {ref: ref$1} = await importShared('vue');



const _sfc_main$2 = {
  __name: 'HistoryTable',
  props: {
  history: {
    type: Array,
    default: () => [],
  },
  failures: {
    type: Array,
    default: () => [],
  },
},
  setup(__props) {



const activeTab = ref$1('history');

return (_ctx, _cache) => {
  const _component_v_tab = _resolveComponent$2("v-tab");
  const _component_v_tabs = _resolveComponent$2("v-tabs");
  const _component_v_window_item = _resolveComponent$2("v-window-item");
  const _component_v_window = _resolveComponent$2("v-window");

  return (_openBlock$2(), _createElementBlock$2("section", _hoisted_1$2, [
    _createVNode$2(_component_v_tabs, {
      modelValue: activeTab.value,
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((activeTab).value = $event)),
      color: "#167A5B",
      density: "comfortable"
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_tab, { value: "history" }, {
          default: _withCtx$2(() => [...(_cache[2] || (_cache[2] = [
            _createTextVNode$2("任务历史", -1)
          ]))]),
          _: 1
        }),
        _createVNode$2(_component_v_tab, { value: "failures" }, {
          default: _withCtx$2(() => [...(_cache[3] || (_cache[3] = [
            _createTextVNode$2("失败记录", -1)
          ]))]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode$2(_component_v_window, {
      modelValue: activeTab.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((activeTab).value = $event))
    }, {
      default: _withCtx$2(() => [
        _createVNode$2(_component_v_window_item, {
          value: "history",
          class: "tab-panel"
        }, {
          default: _withCtx$2(() => [
            (!__props.history.length)
              ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_2$2, "暂无任务历史"))
              : (_openBlock$2(), _createElementBlock$2("div", _hoisted_3$2, [
                  _createElementVNode$2("table", null, [
                    _cache[4] || (_cache[4] = _createElementVNode$2("thead", null, [
                      _createElementVNode$2("tr", null, [
                        _createElementVNode$2("th", null, "时间"),
                        _createElementVNode$2("th", null, "模式"),
                        _createElementVNode$2("th", null, "状态"),
                        _createElementVNode$2("th", null, "秒传"),
                        _createElementVNode$2("th", null, "上传"),
                        _createElementVNode$2("th", null, "失败")
                      ])
                    ], -1)),
                    _createElementVNode$2("tbody", null, [
                      (_openBlock$2(true), _createElementBlock$2(_Fragment$1, null, _renderList$1(__props.history, (item) => {
                        return (_openBlock$2(), _createElementBlock$2("tr", {
                          key: item.id
                        }, [
                          _createElementVNode$2("td", null, _toDisplayString$2(item.ended_at || item.started_at || '-'), 1),
                          _createElementVNode$2("td", null, _toDisplayString$2(item.mode || '-'), 1),
                          _createElementVNode$2("td", null, _toDisplayString$2(item.status || '-'), 1),
                          _createElementVNode$2("td", null, _toDisplayString$2(item.counts?.reused ?? 0), 1),
                          _createElementVNode$2("td", null, _toDisplayString$2(item.counts?.uploaded ?? 0), 1),
                          _createElementVNode$2("td", null, _toDisplayString$2(item.counts?.failed ?? 0), 1)
                        ]))
                      }), 128))
                    ])
                  ])
                ]))
          ]),
          _: 1
        }),
        _createVNode$2(_component_v_window_item, {
          value: "failures",
          class: "tab-panel"
        }, {
          default: _withCtx$2(() => [
            (!__props.failures.length)
              ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_4$2, "暂无失败记录"))
              : (_openBlock$2(), _createElementBlock$2("div", _hoisted_5$2, [
                  _createElementVNode$2("table", null, [
                    _cache[5] || (_cache[5] = _createElementVNode$2("thead", null, [
                      _createElementVNode$2("tr", null, [
                        _createElementVNode$2("th", null, "本地路径"),
                        _createElementVNode$2("th", null, "115 目标"),
                        _createElementVNode$2("th", null, "原因")
                      ])
                    ], -1)),
                    _createElementVNode$2("tbody", null, [
                      (_openBlock$2(true), _createElementBlock$2(_Fragment$1, null, _renderList$1(__props.failures, (item, index) => {
                        return (_openBlock$2(), _createElementBlock$2("tr", { key: index }, [
                          _createElementVNode$2("td", null, _toDisplayString$2(item.local_path || item.source || '-'), 1),
                          _createElementVNode$2("td", null, _toDisplayString$2(item.target_path || item.target || '-'), 1),
                          _createElementVNode$2("td", null, _toDisplayString$2(item.reason || '-'), 1)
                        ]))
                      }), 128))
                    ])
                  ])
                ]))
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const HistoryTable = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-7d228909"]]);

const TaskConsole_vue_vue_type_style_index_0_scoped_67da4d0b_lang = '';

const {createElementVNode:_createElementVNode$1,toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1} = await importShared('vue');


const _hoisted_1$1 = { class: "task-console" };
const _hoisted_2$1 = { class: "console-head" };
const _hoisted_3$1 = { class: "console-phase" };
const _hoisted_4$1 = { class: "console-actions" };
const _hoisted_5$1 = { class: "stat-grid" };


const _sfc_main$1 = {
  __name: 'TaskConsole',
  props: {
  status: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['run-full', 'run-incremental', 'stop', 'refresh'],
  setup(__props, { emit: __emit }) {

const emit = __emit;

const statItems = [
  ['scanned', '扫描'],
  ['planned', '待传'],
  ['reused', '秒传'],
  ['uploaded', '上传'],
  ['failed', '失败'],
];

return (_ctx, _cache) => {
  const _component_v_chip = _resolveComponent$1("v-chip");
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_btn = _resolveComponent$1("v-btn");

  return (_openBlock$1(), _createElementBlock$1("section", _hoisted_1$1, [
    _createElementVNode$1("div", _hoisted_2$1, [
      _createElementVNode$1("div", null, [
        _cache[4] || (_cache[4] = _createElementVNode$1("div", { class: "console-title" }, "任务控制", -1)),
        _createElementVNode$1("div", _hoisted_3$1, _toDisplayString$1(__props.status.message || '未执行'), 1)
      ]),
      _createVNode$1(_component_v_chip, {
        color: __props.status.running ? '#167A5B' : '#66736D',
        variant: "tonal"
      }, {
        default: _withCtx$1(() => [
          _createTextVNode$1(_toDisplayString$1(__props.status.phase || 'idle'), 1)
        ]),
        _: 1
      }, 8, ["color"])
    ]),
    _createElementVNode$1("div", _hoisted_4$1, [
      _createVNode$1(_component_v_btn, {
        color: "#167A5B",
        variant: "flat",
        loading: __props.loading.full,
        disabled: __props.status.running,
        onClick: _cache[0] || (_cache[0] = $event => (emit('run-full')))
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_icon, {
            icon: "mdi-cloud-upload-outline",
            class: "mr-1"
          }),
          _cache[5] || (_cache[5] = _createTextVNode$1("全量上传 ", -1))
        ]),
        _: 1
      }, 8, ["loading", "disabled"]),
      _createVNode$1(_component_v_btn, {
        color: "#245B7A",
        variant: "flat",
        loading: __props.loading.incremental,
        disabled: __props.status.running,
        onClick: _cache[1] || (_cache[1] = $event => (emit('run-incremental')))
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_icon, {
            icon: "mdi-progress-upload",
            class: "mr-1"
          }),
          _cache[6] || (_cache[6] = _createTextVNode$1("增量上传 ", -1))
        ]),
        _: 1
      }, 8, ["loading", "disabled"]),
      _createVNode$1(_component_v_btn, {
        color: "#B42318",
        variant: "tonal",
        disabled: !__props.status.running,
        onClick: _cache[2] || (_cache[2] = $event => (emit('stop')))
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_icon, {
            icon: "mdi-stop-circle-outline",
            class: "mr-1"
          }),
          _cache[7] || (_cache[7] = _createTextVNode$1("停止 ", -1))
        ]),
        _: 1
      }, 8, ["disabled"]),
      _createVNode$1(_component_v_btn, {
        color: "#17201C",
        variant: "text",
        loading: __props.loading.refresh,
        onClick: _cache[3] || (_cache[3] = $event => (emit('refresh')))
      }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_icon, { icon: "mdi-refresh" })
        ]),
        _: 1
      }, 8, ["loading"])
    ]),
    _createElementVNode$1("div", _hoisted_5$1, [
      (_openBlock$1(), _createElementBlock$1(_Fragment, null, _renderList(statItems, ([key, label]) => {
        return _createElementVNode$1("div", {
          key: key,
          class: "stat-cell"
        }, [
          _createElementVNode$1("span", null, _toDisplayString$1(label), 1),
          _createElementVNode$1("strong", null, _toDisplayString$1(__props.status.counts?.[key] ?? 0), 1)
        ])
      }), 64))
    ])
  ]))
}
}

};
const TaskConsole = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-67da4d0b"]]);

const AppPage_vue_vue_type_style_index_0_scoped_7f94cd73_lang = '';

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "app-page" };
const _hoisted_2 = { class: "topbar" };
const _hoisted_3 = { class: "subline" };
const _hoisted_4 = { class: "top-actions" };
const _hoisted_5 = { class: "dashboard-grid" };
const _hoisted_6 = { class: "panel control-panel" };
const _hoisted_7 = { class: "switch-grid" };
const _hoisted_8 = { class: "panel" };
const _hoisted_9 = { class: "panel wide" };
const _hoisted_10 = { class: "panel wide" };
const _hoisted_11 = { class: "history-head" };

const {onMounted,reactive,ref} = await importShared('vue');


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
const status = ref({
  phase: 'idle',
  message: '未执行',
  running: false,
  authorized: false,
  enabled: false,
  counts: { scanned: 0, planned: 0, reused: 0, uploaded: 0, failed: 0 },
});
const history = ref([]);
const failures = ref([]);
const loading = reactive({ config: false, status: false, history: false, full: false, incremental: false, save: false, clear: false });
const snackbar = reactive({ show: false, text: '', color: 'success' });

function toast(text, color = 'success') {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

function applyConfig(value) {
  Object.assign(config, defaultConfig, value || {});
}

async function loadConfig() {
  loading.config = true;
  try {
    const result = await pluginRequest(props.api, '/config');
    applyConfig(normalizeResponse(result, defaultConfig));
  } catch (error) {
    toast(error?.message || '获取配置失败', 'error');
  } finally {
    loading.config = false;
  }
}

async function saveConfig() {
  loading.save = true;
  try {
    const result = await pluginRequest(props.api, '/config', { method: 'POST', body: { ...config } });
    if (!result?.success) throw new Error(result?.message || '保存配置失败')
    applyConfig(result.data || config);
    toast('配置已保存');
    await loadStatus();
  } catch (error) {
    toast(error?.message || '保存配置失败', 'error');
  } finally {
    loading.save = false;
  }
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

async function loadHistory() {
  loading.history = true;
  try {
    const result = await pluginRequest(props.api, '/history');
    if (!result?.success) throw new Error(result?.message || '获取历史失败')
    const data = normalizeResponse(result, {});
    history.value = data.history || [];
    failures.value = data.failures || [];
  } catch (error) {
    toast(error?.message || '获取历史失败', 'error');
  } finally {
    loading.history = false;
  }
}

async function runTask(path, flag) {
  loading[flag] = true;
  try {
    const result = await pluginRequest(props.api, path, { method: 'POST' });
    if (!result?.success) throw new Error(result?.message || '任务启动失败')
    toast(result.message || '任务已启动');
    await loadStatus();
  } catch (error) {
    toast(error?.message || '任务启动失败', 'error');
  } finally {
    loading[flag] = false;
  }
}

async function stopTask() {
  try {
    const result = await pluginRequest(props.api, '/stop', { method: 'POST' });
    if (!result?.success) throw new Error(result?.message || '停止失败')
    toast(result.message || '已请求停止任务');
    await loadStatus();
  } catch (error) {
    toast(error?.message || '停止失败', 'error');
  }
}

async function clearRecords() {
  loading.clear = true;
  try {
    const result = await pluginRequest(props.api, '/clear_records', { method: 'POST' });
    if (!result?.success) throw new Error(result?.message || '清理失败')
    toast('增量记录已清理');
    await loadHistory();
  } catch (error) {
    toast(error?.message || '清理失败', 'error');
  } finally {
    loading.clear = false;
  }
}

async function refreshAll(showMessage = false) {
  await Promise.all([loadStatus(showMessage), loadHistory()]);
}

onMounted(async () => {
  await loadConfig();
  await refreshAll();
});

return (_ctx, _cache) => {
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("main", _hoisted_1, [
    _createElementVNode("header", _hoisted_2, [
      _createElementVNode("div", null, [
        _cache[12] || (_cache[12] = _createElementVNode("div", { class: "title-line" }, [
          _createElementVNode("span", { class: "mark" }, "115"),
          _createElementVNode("h1", null, "媒体上传控制台")
        ], -1)),
        _createElementVNode("div", _hoisted_3, _toDisplayString(status.value.message || '未执行'), 1)
      ]),
      _createElementVNode("div", _hoisted_4, [
        _createVNode(_component_v_chip, {
          color: status.value.authorized ? '#167A5B' : '#B42318',
          variant: "tonal"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(status.value.authorized ? '已授权' : '未授权'), 1)
          ]),
          _: 1
        }, 8, ["color"]),
        _createVNode(_component_v_chip, {
          color: status.value.running ? '#167A5B' : '#66736D',
          variant: "tonal"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(status.value.phase || 'idle'), 1)
          ]),
          _: 1
        }, 8, ["color"]),
        _createVNode(_component_v_btn, {
          color: "#167A5B",
          variant: "flat",
          loading: loading.save,
          onClick: saveConfig
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-content-save-outline",
              class: "mr-1"
            }),
            _cache[13] || (_cache[13] = _createTextVNode("保存 ", -1))
          ]),
          _: 1
        }, 8, ["loading"]),
        _createVNode(_component_v_btn, {
          icon: "mdi-refresh",
          variant: "text",
          loading: loading.status,
          onClick: _cache[0] || (_cache[0] = $event => (refreshAll(true)))
        }, null, 8, ["loading"])
      ])
    ]),
    _createElementVNode("section", _hoisted_5, [
      _createElementVNode("div", _hoisted_6, [
        _createVNode(AuthPanel, {
          api: __props.api,
          config: config,
          "onUpdate:config": applyConfig,
          onToast: toast
        }, null, 8, ["api", "config"]),
        _createVNode(_component_v_divider),
        _createElementVNode("div", _hoisted_7, [
          _createVNode(_component_v_switch, {
            modelValue: config.enabled,
            "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.enabled) = $event)),
            color: "#167A5B",
            label: "启用插件",
            inset: ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_switch, {
            modelValue: config.event_incremental,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.event_incremental) = $event)),
            color: "#167A5B",
            label: "整理完成自动增量",
            inset: ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_switch, {
            modelValue: config.upload_existing_sidecars,
            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.upload_existing_sidecars) = $event)),
            color: "#167A5B",
            label: "上传已有附属文件",
            inset: ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_switch, {
            modelValue: config.scrape_before_upload,
            "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.scrape_before_upload) = $event)),
            color: "#167A5B",
            label: "上传前刮削",
            inset: ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_switch, {
            modelValue: config.scrape_overwrite,
            "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.scrape_overwrite) = $event)),
            color: "#B7791F",
            label: "刮削覆盖已有文件",
            inset: ""
          }, null, 8, ["modelValue"])
        ]),
        _createVNode(_component_v_text_field, {
          modelValue: config.cron,
          "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.cron) = $event)),
          label: "定时增量 Cron",
          variant: "outlined",
          density: "comfortable",
          "hide-details": ""
        }, null, 8, ["modelValue"])
      ]),
      _createElementVNode("div", _hoisted_8, [
        _createVNode(TaskConsole, {
          status: status.value,
          loading: loading,
          onRunFull: _cache[7] || (_cache[7] = $event => (runTask('/run_full', 'full'))),
          onRunIncremental: _cache[8] || (_cache[8] = $event => (runTask('/run_incremental', 'incremental'))),
          onStop: stopTask,
          onRefresh: _cache[9] || (_cache[9] = $event => (refreshAll(true)))
        }, null, 8, ["status", "loading"])
      ]),
      _createElementVNode("div", _hoisted_9, [
        _createVNode(PathMappingEditor, {
          mappings: config.path_mappings,
          "onUpdate:mappings": _cache[10] || (_cache[10] = $event => ((config.path_mappings) = $event))
        }, null, 8, ["mappings"])
      ]),
      _createElementVNode("div", _hoisted_10, [
        _createElementVNode("div", _hoisted_11, [
          _cache[15] || (_cache[15] = _createElementVNode("div", null, [
            _createElementVNode("div", { class: "section-title" }, "历史与失败"),
            _createElementVNode("div", { class: "section-subtitle" }, "最近任务、失败原因和增量记录入口")
          ], -1)),
          _createVNode(_component_v_btn, {
            color: "#B42318",
            variant: "tonal",
            loading: loading.clear,
            onClick: clearRecords
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                icon: "mdi-database-remove-outline",
                class: "mr-1"
              }),
              _cache[14] || (_cache[14] = _createTextVNode("清理增量记录 ", -1))
            ]),
            _: 1
          }, 8, ["loading"])
        ]),
        _createVNode(HistoryTable, {
          history: history.value,
          failures: failures.value
        }, null, 8, ["history", "failures"])
      ])
    ]),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((snackbar.show) = $event)),
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
const AppPage = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-7f94cd73"]]);

export { AppPage as default };
