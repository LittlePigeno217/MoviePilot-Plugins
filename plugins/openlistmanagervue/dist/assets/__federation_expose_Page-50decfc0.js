import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,withModifiers:_withModifiers} = await importShared('vue');

const _hoisted_1 = { class: "plugin-page" };
const _hoisted_2 = { class: "page-header" };
const _hoisted_3 = { class: "page-actions" };
const _hoisted_4 = ["disabled"];
const _hoisted_5 = { class: "btn-icon" };
const _hoisted_6 = { class: "btn-text" };
const _hoisted_7 = { class: "message-icon" };
const _hoisted_8 = { class: "message-text" };
const _hoisted_9 = { class: "main-content" };
const _hoisted_10 = { class: "stats-cards" };
const _hoisted_11 = { class: "stat-card" };
const _hoisted_12 = { class: "stat-content" };
const _hoisted_13 = { class: "stat-value" };
const _hoisted_14 = { class: "stat-card" };
const _hoisted_15 = { class: "stat-content" };
const _hoisted_16 = { class: "stat-value" };
const _hoisted_17 = { class: "stat-card" };
const _hoisted_18 = { class: "stat-content" };
const _hoisted_19 = { class: "stat-value" };
const _hoisted_20 = { class: "stat-card" };
const _hoisted_21 = { class: "stat-content" };
const _hoisted_22 = { class: "stat-value" };
const _hoisted_23 = { class: "feature-card full-width" };
const _hoisted_24 = { class: "card-body" };
const _hoisted_25 = { class: "media-counts-list" };
const _hoisted_26 = { class: "media-count-dir" };
const _hoisted_27 = { class: "media-count-size" };
const _hoisted_28 = { class: "media-count-value" };
const _hoisted_29 = {
  key: 0,
  class: "empty-state"
};
const _hoisted_30 = { class: "feature-card full-width" };
const _hoisted_31 = { class: "card-body" };
const _hoisted_32 = { class: "history-list" };
const _hoisted_33 = { class: "history-time" };
const _hoisted_34 = { class: "history-content" };
const _hoisted_35 = { class: "history-description" };
const _hoisted_36 = { class: "history-status" };
const _hoisted_37 = ["onClick"];
const _hoisted_38 = { class: "modal-body" };
const _hoisted_39 = { class: "overview-card" };
const _hoisted_40 = { class: "overview-grid" };
const _hoisted_41 = { class: "overview-item" };
const _hoisted_42 = { class: "overview-value" };
const _hoisted_43 = { class: "overview-item" };
const _hoisted_44 = { class: "overview-value" };
const _hoisted_45 = { class: "overview-item" };
const _hoisted_46 = { class: "overview-value" };
const _hoisted_47 = { class: "overview-item" };
const _hoisted_48 = { class: "overview-value" };
const _hoisted_49 = { class: "files-section" };
const _hoisted_50 = { class: "section-header" };
const _hoisted_51 = { class: "section-info" };
const _hoisted_52 = { class: "files-container" };
const _hoisted_53 = { class: "data-table files-table" };
const _hoisted_54 = { class: "file-name-cell" };
const _hoisted_55 = { class: "file-info" };
const _hoisted_56 = { class: "file-name" };
const _hoisted_57 = {
  key: 0,
  class: "file-source"
};
const _hoisted_58 = { class: "file-size-cell" };
const _hoisted_59 = { class: "file-path-cell" };
const _hoisted_60 = {
  key: 0,
  class: "empty-state"
};
const {ref,onMounted} = await importShared('vue');

const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Page",
  props: {
    api: {}
  },
  emits: ["action", "switch", "close"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const pluginStatus = ref("已禁用");
    const nextRunTime = ref("暂无计划");
    const totalFiles = ref(0);
    const copiedFiles = ref(0);
    const mediaCounts = ref([]);
    const copyHistory = ref([]);
    const isRunning = ref(false);
    const message = ref("");
    const showDetails = ref(false);
    const currentHistory = ref(null);
    const historyDetails = ref([]);
    const formatFileSize = (bytes) => {
      if (bytes === 0)
        return "0 B";
      const k = 1024;
      const sizes = ["B", "KB", "MB", "GB", "TB"];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    };
    async function fetchStatus() {
      if (!props.api || !props.api.get) {
        message.value = "API对象不可用";
        return;
      }
      try {
        const result = await props.api.get("/plugin/OpenListManagerVue/status");
        if (result && !result.error) {
          pluginStatus.value = result.enabled ? "已启用" : "已禁用";
          nextRunTime.value = result.next_run_time || "暂无计划";
          totalFiles.value = result.target_files_count || 0;
          copiedFiles.value = result.copied_files_count || 0;
          if (result.media_counts) {
            mediaCounts.value = result.media_counts;
          } else {
            mediaCounts.value = [];
          }
          if (result.copy_history) {
            copyHistory.value = result.copy_history.map((item, index) => ({
              id: index + 1,
              time: item.timestamp,
              description: `复制 ${item.total} 个文件（媒体: ${item.media}，刮削: ${item.scraper}）`,
              status: "success",
              files: item.files || []
            }));
          }
        }
      } catch (error) {
        console.error("获取状态失败:", error);
      }
    }
    function notifyRefresh() {
      emit("action");
      fetchStatus();
    }
    function notifySwitch() {
      emit("switch");
    }
    function notifyClose() {
      emit("close");
    }
    async function runTask() {
      if (!props.api || !props.api.post) {
        message.value = "API对象不可用";
        return;
      }
      isRunning.value = true;
      message.value = "正在执行任务...";
      try {
        const result = await props.api.post("/plugin/OpenListManagerVue/run");
        if (result.error) {
          message.value = `执行失败: ${result.message}`;
        } else {
          message.value = "任务已开始执行";
          notifyRefresh();
        }
      } catch (error) {
        console.error("API调用错误:", error);
        message.value = `执行失败: ${error.message || error}`;
      } finally {
        isRunning.value = false;
      }
    }
    function viewDetails(item) {
      currentHistory.value = item;
      historyDetails.value = item.files || [];
      showDetails.value = true;
    }
    function closeDetails() {
      showDetails.value = false;
      currentHistory.value = null;
      historyDetails.value = [];
    }
    onMounted(() => {
      fetchStatus();
    });
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", _hoisted_1, [
        _createElementVNode("div", _hoisted_2, [
          _cache[4] || (_cache[4] = _createElementVNode("h1", null, "OpenList管理器", -1)),
          _createElementVNode("div", _hoisted_3, [
            _createElementVNode("button", {
              class: _normalizeClass(["btn btn-primary", isRunning.value ? "btn-loading" : ""]),
              onClick: runTask,
              disabled: isRunning.value,
              title: "立即执行任务"
            }, [
              _createElementVNode("span", _hoisted_5, _toDisplayString(isRunning.value ? "⏳" : "▶️"), 1),
              _createElementVNode("span", _hoisted_6, _toDisplayString(isRunning.value ? "执行中..." : "立即执行"), 1)
            ], 10, _hoisted_4),
            _createElementVNode("button", {
              class: "btn btn-refresh",
              onClick: notifyRefresh,
              title: "刷新数据"
            }, [..._cache[1] || (_cache[1] = [
              _createElementVNode("span", { class: "btn-icon" }, "🔄", -1),
              _createElementVNode("span", { class: "btn-text" }, "刷新", -1)
            ])]),
            _createElementVNode("button", {
              class: "btn btn-config",
              onClick: notifySwitch,
              title: "进入配置页面"
            }, [..._cache[2] || (_cache[2] = [
              _createElementVNode("span", { class: "btn-icon" }, "⚙️", -1),
              _createElementVNode("span", { class: "btn-text" }, "配置", -1)
            ])]),
            _createElementVNode("button", {
              class: "btn btn-close",
              onClick: notifyClose,
              title: "关闭当前页面"
            }, [..._cache[3] || (_cache[3] = [
              _createElementVNode("span", { class: "btn-icon" }, "✕", -1),
              _createElementVNode("span", { class: "btn-text" }, "关闭", -1)
            ])])
          ])
        ]),
        message.value ? (_openBlock(), _createElementBlock("div", {
          key: 0,
          class: _normalizeClass(["message-alert", isRunning.value ? "message-loading" : message.value.includes("失败") ? "message-error" : "message-success"])
        }, [
          _createElementVNode("span", _hoisted_7, _toDisplayString(isRunning.value ? "⏳" : message.value.includes("失败") ? "❌" : "✅"), 1),
          _createElementVNode("span", _hoisted_8, _toDisplayString(message.value), 1)
        ], 2)) : _createCommentVNode("", true),
        _createElementVNode("div", _hoisted_9, [
          _createElementVNode("div", _hoisted_10, [
            _createElementVNode("div", _hoisted_11, [
              _createElementVNode("div", {
                class: _normalizeClass(["stat-icon", pluginStatus.value === "已启用" ? "stat-running" : "stat-stopped"])
              }, _toDisplayString(pluginStatus.value === "已启用" ? "⚡" : "⏸️"), 3),
              _createElementVNode("div", _hoisted_12, [
                _createElementVNode("div", _hoisted_13, _toDisplayString(pluginStatus.value), 1),
                _cache[5] || (_cache[5] = _createElementVNode("div", { class: "stat-label" }, "插件状态", -1))
              ])
            ]),
            _createElementVNode("div", _hoisted_14, [
              _cache[7] || (_cache[7] = _createElementVNode("div", { class: "stat-icon stat-schedule" }, "⏰", -1)),
              _createElementVNode("div", _hoisted_15, [
                _createElementVNode("div", _hoisted_16, _toDisplayString(nextRunTime.value), 1),
                _cache[6] || (_cache[6] = _createElementVNode("div", { class: "stat-label" }, "下次运行", -1))
              ])
            ]),
            _createElementVNode("div", _hoisted_17, [
              _cache[9] || (_cache[9] = _createElementVNode("div", { class: "stat-icon stat-files" }, "📁", -1)),
              _createElementVNode("div", _hoisted_18, [
                _createElementVNode("div", _hoisted_19, _toDisplayString(totalFiles.value), 1),
                _cache[8] || (_cache[8] = _createElementVNode("div", { class: "stat-label" }, "目标文件数", -1))
              ])
            ]),
            _createElementVNode("div", _hoisted_20, [
              _cache[11] || (_cache[11] = _createElementVNode("div", { class: "stat-icon stat-completed" }, "✓", -1)),
              _createElementVNode("div", _hoisted_21, [
                _createElementVNode("div", _hoisted_22, _toDisplayString(copiedFiles.value), 1),
                _cache[10] || (_cache[10] = _createElementVNode("div", { class: "stat-label" }, "已完成", -1))
              ])
            ])
          ]),
          _createElementVNode("div", _hoisted_23, [
            _cache[13] || (_cache[13] = _createElementVNode("div", { class: "card-header" }, [
              _createElementVNode("h2", null, "当前媒体数量")
            ], -1)),
            _createElementVNode("div", _hoisted_24, [
              _createElementVNode("div", _hoisted_25, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(mediaCounts.value, (item, index) => {
                  return _openBlock(), _createElementBlock("div", {
                    key: index,
                    class: "media-count-item"
                  }, [
                    _createElementVNode("div", _hoisted_26, _toDisplayString(item.dir_name), 1),
                    _createElementVNode("div", _hoisted_27, _toDisplayString(formatFileSize(item.size)), 1),
                    _createElementVNode("div", _hoisted_28, _toDisplayString(item.count) + " 个媒体文件", 1)
                  ]);
                }), 128)),
                mediaCounts.value.length === 0 ? (_openBlock(), _createElementBlock("div", _hoisted_29, [..._cache[12] || (_cache[12] = [
                  _createElementVNode("div", { class: "empty-icon" }, "📁", -1),
                  _createElementVNode("div", { class: "empty-title" }, "暂无媒体数据", -1),
                  _createElementVNode("div", { class: "empty-desc" }, "请确保插件已启用并正确配置了目标目录", -1)
                ])])) : _createCommentVNode("", true)
              ])
            ])
          ]),
          _createElementVNode("div", _hoisted_30, [
            _cache[15] || (_cache[15] = _createElementVNode("div", { class: "card-header" }, [
              _createElementVNode("h2", null, "复制历史")
            ], -1)),
            _createElementVNode("div", _hoisted_31, [
              _createElementVNode("div", _hoisted_32, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(copyHistory.value, (item) => {
                  return _openBlock(), _createElementBlock("div", {
                    key: item.id,
                    class: "history-item"
                  }, [
                    _createElementVNode("div", _hoisted_33, _toDisplayString(item.time), 1),
                    _createElementVNode("div", _hoisted_34, [
                      _createElementVNode("div", _hoisted_35, _toDisplayString(item.description), 1)
                    ]),
                    _createElementVNode("div", _hoisted_36, [
                      _createElementVNode("button", {
                        class: "btn btn-sm",
                        onClick: ($event) => viewDetails(item)
                      }, [..._cache[14] || (_cache[14] = [
                        _createElementVNode("span", { class: "btn-icon" }, "👁️", -1),
                        _createElementVNode("span", { class: "btn-text" }, "查看详情", -1)
                      ])], 8, _hoisted_37)
                    ])
                  ]);
                }), 128))
              ])
            ])
          ]),
          showDetails.value ? (_openBlock(), _createElementBlock("div", {
            key: 0,
            class: "modal-overlay",
            onClick: closeDetails
          }, [
            _createElementVNode("div", {
              class: "modal-content",
              onClick: _cache[0] || (_cache[0] = _withModifiers(() => {
              }, ["stop"]))
            }, [
              _createElementVNode("div", { class: "modal-header" }, [
                _cache[17] || (_cache[17] = _createElementVNode("div", { class: "header-content" }, [
                  _createElementVNode("h3", null, "任务详情"),
                  _createElementVNode("div", { class: "header-subtitle" }, "查看任务的详细执行情况")
                ], -1)),
                _createElementVNode("button", {
                  class: "btn btn-close btn-sm",
                  onClick: closeDetails,
                  title: "关闭"
                }, [..._cache[16] || (_cache[16] = [
                  _createElementVNode("span", { class: "btn-icon" }, "✕", -1)
                ])])
              ]),
              _createElementVNode("div", _hoisted_38, [
                _createElementVNode("div", _hoisted_39, [
                  _cache[22] || (_cache[22] = _createElementVNode("div", { class: "overview-title" }, "任务概览", -1)),
                  _createElementVNode("div", _hoisted_40, [
                    _createElementVNode("div", _hoisted_41, [
                      _cache[18] || (_cache[18] = _createElementVNode("div", { class: "overview-label" }, "执行时间", -1)),
                      _createElementVNode("div", _hoisted_42, _toDisplayString(currentHistory.value?.time), 1)
                    ]),
                    _createElementVNode("div", _hoisted_43, [
                      _cache[19] || (_cache[19] = _createElementVNode("div", { class: "overview-label" }, "任务描述", -1)),
                      _createElementVNode("div", _hoisted_44, _toDisplayString(currentHistory.value?.description), 1)
                    ]),
                    _createElementVNode("div", _hoisted_45, [
                      _cache[20] || (_cache[20] = _createElementVNode("div", { class: "overview-label" }, "源目录", -1)),
                      _createElementVNode("div", _hoisted_46, _toDisplayString(currentHistory.value?.source_dir || "N/A"), 1)
                    ]),
                    _createElementVNode("div", _hoisted_47, [
                      _cache[21] || (_cache[21] = _createElementVNode("div", { class: "overview-label" }, "目标目录", -1)),
                      _createElementVNode("div", _hoisted_48, _toDisplayString(currentHistory.value?.target_dir || "N/A"), 1)
                    ])
                  ])
                ]),
                _createElementVNode("div", _hoisted_49, [
                  _createElementVNode("div", _hoisted_50, [
                    _cache[23] || (_cache[23] = _createElementVNode("h4", null, "文件列表", -1)),
                    _createElementVNode("div", _hoisted_51, "共 " + _toDisplayString(historyDetails.value.length) + " 个文件", 1)
                  ]),
                  _createElementVNode("div", _hoisted_52, [
                    _createElementVNode("table", _hoisted_53, [
                      _cache[24] || (_cache[24] = _createElementVNode("thead", null, [
                        _createElementVNode("tr", null, [
                          _createElementVNode("th", { class: "file-name-col" }, "文件名"),
                          _createElementVNode("th", { class: "file-size-col" }, "大小"),
                          _createElementVNode("th", { class: "file-path-col" }, "目标路径")
                        ])
                      ], -1)),
                      _createElementVNode("tbody", null, [
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(historyDetails.value, (item, index) => {
                          return _openBlock(), _createElementBlock("tr", {
                            key: index,
                            class: "file-row"
                          }, [
                            _createElementVNode("td", _hoisted_54, [
                              _createElementVNode("div", _hoisted_55, [
                                _createElementVNode("div", _hoisted_56, _toDisplayString(item.name), 1),
                                item.source_path ? (_openBlock(), _createElementBlock("div", _hoisted_57, " 源: " + _toDisplayString(item.source_path), 1)) : _createCommentVNode("", true)
                              ])
                            ]),
                            _createElementVNode("td", _hoisted_58, _toDisplayString(item.size), 1),
                            _createElementVNode("td", _hoisted_59, _toDisplayString(item.path), 1)
                          ]);
                        }), 128))
                      ])
                    ]),
                    historyDetails.value.length === 0 ? (_openBlock(), _createElementBlock("div", _hoisted_60, [..._cache[25] || (_cache[25] = [
                      _createElementVNode("div", { class: "empty-icon" }, "📁", -1),
                      _createElementVNode("div", { class: "empty-title" }, "暂无文件数据", -1),
                      _createElementVNode("div", { class: "empty-desc" }, "本次任务没有成功复制的文件", -1)
                    ])])) : _createCommentVNode("", true)
                  ])
                ])
              ]),
              _createElementVNode("div", { class: "modal-footer" }, [
                _createElementVNode("button", {
                  class: "btn btn-secondary",
                  onClick: closeDetails
                }, "关闭")
              ])
            ])
          ])) : _createCommentVNode("", true)
        ])
      ]);
    };
  }
});

const Page_vue_vue_type_style_index_0_scoped_d58951b1_lang = '';

const Page = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-d58951b1"]]);

export { Page as default };
