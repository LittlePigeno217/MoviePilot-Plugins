import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,vModelText:_vModelText,withDirectives:_withDirectives,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,vModelCheckbox:_vModelCheckbox,createCommentVNode:_createCommentVNode} = await importShared('vue');

const _hoisted_1 = { class: "plugin-config" };
const _hoisted_2 = { class: "config-header" };
const _hoisted_3 = { class: "header-actions" };
const _hoisted_4 = ["disabled"];
const _hoisted_5 = { class: "btn-icon" };
const _hoisted_6 = { class: "btn-text" };
const _hoisted_7 = { class: "config-content" };
const _hoisted_8 = { class: "config-cards" };
const _hoisted_9 = { class: "feature-card" };
const _hoisted_10 = { class: "card-body" };
const _hoisted_11 = { class: "form-section" };
const _hoisted_12 = { class: "form-grid" };
const _hoisted_13 = { class: "form-group" };
const _hoisted_14 = { class: "form-group" };
const _hoisted_15 = { class: "feature-card" };
const _hoisted_16 = { class: "card-body" };
const _hoisted_17 = { class: "directory-config" };
const _hoisted_18 = { class: "directory-grid" };
const _hoisted_19 = { class: "directory-section" };
const _hoisted_20 = { class: "directory-selector" };
const _hoisted_21 = { class: "directory-tree-container" };
const _hoisted_22 = { class: "directory-tree-header" };
const _hoisted_23 = { class: "directory-count" };
const _hoisted_24 = { class: "directory-tree" };
const _hoisted_25 = ["onClick"];
const _hoisted_26 = { class: "expand-icon" };
const _hoisted_27 = ["value"];
const _hoisted_28 = { class: "directory-name" };
const _hoisted_29 = {
  key: 0,
  class: "directory-children"
};
const _hoisted_30 = ["onClick"];
const _hoisted_31 = { class: "expand-icon" };
const _hoisted_32 = ["value"];
const _hoisted_33 = { class: "directory-name" };
const _hoisted_34 = {
  key: 0,
  class: "directory-children"
};
const _hoisted_35 = ["onClick"];
const _hoisted_36 = { class: "expand-icon" };
const _hoisted_37 = ["value"];
const _hoisted_38 = { class: "directory-name" };
const _hoisted_39 = {
  key: 0,
  class: "directory-children"
};
const _hoisted_40 = { class: "directory-content" };
const _hoisted_41 = ["value"];
const _hoisted_42 = { class: "directory-name" };
const _hoisted_43 = { class: "directory-section" };
const _hoisted_44 = { class: "directory-selector" };
const _hoisted_45 = { class: "directory-tree-container" };
const _hoisted_46 = { class: "directory-tree-header" };
const _hoisted_47 = { class: "directory-count" };
const _hoisted_48 = { class: "directory-tree" };
const _hoisted_49 = ["onClick"];
const _hoisted_50 = { class: "expand-icon" };
const _hoisted_51 = ["value"];
const _hoisted_52 = { class: "directory-name" };
const _hoisted_53 = {
  key: 0,
  class: "directory-children"
};
const _hoisted_54 = ["onClick"];
const _hoisted_55 = { class: "expand-icon" };
const _hoisted_56 = ["value"];
const _hoisted_57 = { class: "directory-name" };
const _hoisted_58 = {
  key: 0,
  class: "directory-children"
};
const _hoisted_59 = ["onClick"];
const _hoisted_60 = { class: "expand-icon" };
const _hoisted_61 = ["value"];
const _hoisted_62 = { class: "directory-name" };
const _hoisted_63 = {
  key: 0,
  class: "directory-children"
};
const _hoisted_64 = { class: "directory-content" };
const _hoisted_65 = ["value"];
const _hoisted_66 = { class: "directory-name" };
const _hoisted_67 = { class: "feature-card" };
const _hoisted_68 = { class: "card-body" };
const _hoisted_69 = { class: "form-section" };
const _hoisted_70 = { class: "form-grid" };
const _hoisted_71 = { class: "form-group" };
const _hoisted_72 = { class: "form-group" };
const _hoisted_73 = { class: "form-checkbox-label" };
const _hoisted_74 = { class: "feature-card" };
const _hoisted_75 = { class: "card-body" };
const _hoisted_76 = { class: "form-section" };
const _hoisted_77 = { class: "form-grid" };
const _hoisted_78 = { class: "form-group" };
const _hoisted_79 = { class: "form-checkbox-label" };
const _hoisted_80 = { class: "form-group" };
const _hoisted_81 = { class: "form-checkbox-label" };
const {ref,onMounted,reactive} = await importShared('vue');

const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    api: {}
  },
  emits: ["action", "close"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const isLoading = ref(false);
    const isSaving = ref(false);
    const message = ref("");
    const directories = ref([]);
    const sourceExpanded = ref(/* @__PURE__ */ new Set());
    const targetExpanded = ref(/* @__PURE__ */ new Set());
    const config = reactive({
      enable: true,
      openlist_url: "",
      openlist_token: "",
      openlist_source_dir: "",
      openlist_target_dir: "",
      openlist_source_dirs: [],
      openlist_target_dirs: [],
      enable_custom_suffix: false,
      use_moviepilot_config: true,
      enable_wechat_notify: false,
      cron: "30 3 * * *",
      onlyonce: false
    });
    const initialConfig = reactive({ ...config });
    const toggleSourceExpanded = (path) => {
      if (sourceExpanded.value.has(path)) {
        sourceExpanded.value.delete(path);
      } else {
        sourceExpanded.value.add(path);
      }
    };
    const toggleTargetExpanded = (path) => {
      if (targetExpanded.value.has(path)) {
        targetExpanded.value.delete(path);
      } else {
        targetExpanded.value.add(path);
      }
    };
    async function fetchDirectories() {
      if (!props.api || !props.api.get) {
        message.value = "API对象不可用";
        return;
      }
      isLoading.value = true;
      message.value = "正在获取目录列表...";
      try {
        await saveConfig(true);
        const result = await props.api.get("/plugin/OpenListManagerVue/directories");
        if (result && !result.error) {
          directories.value = result.directory_structure.children || [];
          message.value = "目录列表获取成功";
        } else {
          message.value = `获取目录列表失败: ${result.message || "未知错误"}`;
        }
      } catch (error) {
        message.value = `获取目录列表失败: ${error}`;
        console.error("获取目录列表失败:", error);
      } finally {
        isLoading.value = false;
      }
    }
    async function fetchConfig() {
      if (!props.api || !props.api.get) {
        message.value = "API对象不可用";
        return;
      }
      try {
        const result = await props.api.get("/plugin/OpenListManagerVue/config");
        if (result && !result.error) {
          Object.assign(config, result);
          Object.assign(initialConfig, result);
          await fetchDirectories();
        }
      } catch (error) {
        console.error("获取配置失败:", error);
      }
    }
    async function saveConfig(silent = false) {
      if (!props.api || !props.api.post) {
        message.value = "API对象不可用";
        return;
      }
      isSaving.value = true;
      if (!silent) {
        message.value = "正在保存配置...";
      }
      try {
        const result = await props.api.post("/plugin/OpenListManagerVue/config", config);
        if (result && !result.error) {
          message.value = "配置保存成功";
          Object.assign(initialConfig, config);
          emit("action");
          return true;
        } else {
          message.value = `保存配置失败: ${result.message || "未知错误"}`;
          return false;
        }
      } catch (error) {
        message.value = `保存配置失败: ${error}`;
        console.error("保存配置失败:", error);
        return false;
      } finally {
        isSaving.value = false;
      }
    }
    function resetConfig() {
      Object.assign(config, initialConfig);
      message.value = "配置已重置为初始值";
    }
    function notifyClose() {
      emit("close");
    }
    onMounted(() => {
      fetchConfig();
    });
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", _hoisted_1, [
        _createElementVNode("div", _hoisted_2, [
          _cache[17] || (_cache[17] = _createElementVNode("h1", null, "OpenList管理器配置", -1)),
          _createElementVNode("div", _hoisted_3, [
            _createElementVNode("button", {
              class: "btn btn-secondary",
              onClick: fetchDirectories,
              title: "刷新目录列表"
            }, [..._cache[14] || (_cache[14] = [
              _createElementVNode("span", { class: "btn-icon" }, "📂", -1),
              _createElementVNode("span", { class: "btn-text" }, "刷新目录", -1)
            ])]),
            _createElementVNode("button", {
              class: "btn btn-secondary",
              onClick: resetConfig,
              title: "重置配置"
            }, [..._cache[15] || (_cache[15] = [
              _createElementVNode("span", { class: "btn-icon" }, "🔄", -1),
              _createElementVNode("span", { class: "btn-text" }, "重置", -1)
            ])]),
            _createElementVNode("button", {
              class: "btn btn-primary",
              onClick: saveConfig,
              disabled: isSaving.value,
              title: "保存配置"
            }, [
              _createElementVNode("span", _hoisted_5, _toDisplayString(isSaving.value ? "⏳" : "💾"), 1),
              _createElementVNode("span", _hoisted_6, _toDisplayString(isSaving.value ? "保存中..." : "保存配置"), 1)
            ], 8, _hoisted_4),
            _createElementVNode("button", {
              class: "btn btn-secondary",
              onClick: notifyClose,
              title: "关闭当前页面"
            }, [..._cache[16] || (_cache[16] = [
              _createElementVNode("span", { class: "btn-icon" }, "✕", -1),
              _createElementVNode("span", { class: "btn-text" }, "关闭", -1)
            ])])
          ])
        ]),
        _createElementVNode("div", _hoisted_7, [
          _createElementVNode("div", _hoisted_8, [
            _createElementVNode("div", _hoisted_9, [
              _cache[22] || (_cache[22] = _createElementVNode("div", { class: "card-header" }, [
                _createElementVNode("h2", null, "基础配置")
              ], -1)),
              _createElementVNode("div", _hoisted_10, [
                _createElementVNode("div", _hoisted_11, [
                  _createElementVNode("div", _hoisted_12, [
                    _createElementVNode("div", _hoisted_13, [
                      _cache[18] || (_cache[18] = _createElementVNode("label", { class: "form-label" }, [
                        _createElementVNode("span", { class: "required-mark" }, "*"),
                        _createTextVNode(" OpenList URL ")
                      ], -1)),
                      _withDirectives(_createElementVNode("input", {
                        type: "text",
                        class: "form-control",
                        "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => config.openlist_url = $event),
                        placeholder: "请输入OpenList服务器地址，如 http://localhost:5244"
                      }, null, 512), [
                        [_vModelText, config.openlist_url]
                      ]),
                      _cache[19] || (_cache[19] = _createElementVNode("div", { class: "form-hint" }, "请确保URL格式正确，不包含尾部斜杠", -1))
                    ]),
                    _createElementVNode("div", _hoisted_14, [
                      _cache[20] || (_cache[20] = _createElementVNode("label", { class: "form-label" }, [
                        _createElementVNode("span", { class: "required-mark" }, "*"),
                        _createTextVNode(" OpenList Token ")
                      ], -1)),
                      _withDirectives(_createElementVNode("input", {
                        type: "text",
                        class: "form-control",
                        "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => config.openlist_token = $event),
                        placeholder: "请输入OpenList访问令牌"
                      }, null, 512), [
                        [_vModelText, config.openlist_token]
                      ]),
                      _cache[21] || (_cache[21] = _createElementVNode("div", { class: "form-hint" }, "从OpenList后台获取访问令牌", -1))
                    ])
                  ])
                ])
              ])
            ]),
            _createElementVNode("div", _hoisted_15, [
              _cache[27] || (_cache[27] = _createElementVNode("div", { class: "card-header" }, [
                _createElementVNode("h2", null, "目录配置")
              ], -1)),
              _createElementVNode("div", _hoisted_16, [
                _createElementVNode("div", _hoisted_17, [
                  _createElementVNode("div", _hoisted_18, [
                    _createElementVNode("div", _hoisted_19, [
                      _cache[24] || (_cache[24] = _createElementVNode("h3", null, "源目录配置", -1)),
                      _createElementVNode("div", _hoisted_20, [
                        _createElementVNode("div", _hoisted_21, [
                          _createElementVNode("div", _hoisted_22, [
                            _cache[23] || (_cache[23] = _createElementVNode("span", null, "源目录列表", -1)),
                            _createElementVNode("span", _hoisted_23, "(" + _toDisplayString(sourceExpanded.value.size) + "/" + _toDisplayString(directories.value.length) + ")", 1)
                          ]),
                          _createElementVNode("div", _hoisted_24, [
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(directories.value, (dir) => {
                              return _openBlock(), _createElementBlock("div", {
                                key: dir.path,
                                class: "directory-item"
                              }, [
                                _createElementVNode("div", {
                                  class: "directory-content",
                                  onClick: ($event) => toggleSourceExpanded(dir.path)
                                }, [
                                  _createElementVNode("span", _hoisted_26, _toDisplayString(sourceExpanded.value.has(dir.path) ? "▼" : "▶"), 1),
                                  _withDirectives(_createElementVNode("input", {
                                    type: "checkbox",
                                    "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => config.openlist_source_dirs = $event),
                                    value: dir.path,
                                    class: "directory-checkbox"
                                  }, null, 8, _hoisted_27), [
                                    [_vModelCheckbox, config.openlist_source_dirs]
                                  ]),
                                  _createElementVNode("span", _hoisted_28, _toDisplayString(dir.name), 1)
                                ], 8, _hoisted_25),
                                sourceExpanded.value.has(dir.path) && dir.children && dir.children.length > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_29, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(dir.children, (subdir) => {
                                    return _openBlock(), _createElementBlock("div", {
                                      key: subdir.path,
                                      class: "directory-item"
                                    }, [
                                      _createElementVNode("div", {
                                        class: "directory-content",
                                        onClick: ($event) => toggleSourceExpanded(subdir.path)
                                      }, [
                                        _createElementVNode("span", _hoisted_31, _toDisplayString(sourceExpanded.value.has(subdir.path) ? "▼" : "▶"), 1),
                                        _withDirectives(_createElementVNode("input", {
                                          type: "checkbox",
                                          "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => config.openlist_source_dirs = $event),
                                          value: subdir.path,
                                          class: "directory-checkbox"
                                        }, null, 8, _hoisted_32), [
                                          [_vModelCheckbox, config.openlist_source_dirs]
                                        ]),
                                        _createElementVNode("span", _hoisted_33, _toDisplayString(subdir.name), 1)
                                      ], 8, _hoisted_30),
                                      sourceExpanded.value.has(subdir.path) && subdir.children && subdir.children.length > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_34, [
                                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(subdir.children, (deepdir) => {
                                          return _openBlock(), _createElementBlock("div", {
                                            key: deepdir.path,
                                            class: "directory-item"
                                          }, [
                                            _createElementVNode("div", {
                                              class: "directory-content",
                                              onClick: ($event) => toggleSourceExpanded(deepdir.path)
                                            }, [
                                              _createElementVNode("span", _hoisted_36, _toDisplayString(sourceExpanded.value.has(deepdir.path) ? "▼" : "▶"), 1),
                                              _withDirectives(_createElementVNode("input", {
                                                type: "checkbox",
                                                "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => config.openlist_source_dirs = $event),
                                                value: deepdir.path,
                                                class: "directory-checkbox"
                                              }, null, 8, _hoisted_37), [
                                                [_vModelCheckbox, config.openlist_source_dirs]
                                              ]),
                                              _createElementVNode("span", _hoisted_38, _toDisplayString(deepdir.name), 1)
                                            ], 8, _hoisted_35),
                                            sourceExpanded.value.has(deepdir.path) && deepdir.children && deepdir.children.length > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_39, [
                                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(deepdir.children, (fourdir) => {
                                                return _openBlock(), _createElementBlock("div", {
                                                  key: fourdir.path,
                                                  class: "directory-item"
                                                }, [
                                                  _createElementVNode("div", _hoisted_40, [
                                                    _withDirectives(_createElementVNode("input", {
                                                      type: "checkbox",
                                                      "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => config.openlist_source_dirs = $event),
                                                      value: fourdir.path,
                                                      class: "directory-checkbox"
                                                    }, null, 8, _hoisted_41), [
                                                      [_vModelCheckbox, config.openlist_source_dirs]
                                                    ]),
                                                    _createElementVNode("span", _hoisted_42, _toDisplayString(fourdir.name), 1)
                                                  ])
                                                ]);
                                              }), 128))
                                            ])) : _createCommentVNode("", true)
                                          ]);
                                        }), 128))
                                      ])) : _createCommentVNode("", true)
                                    ]);
                                  }), 128))
                                ])) : _createCommentVNode("", true)
                              ]);
                            }), 128))
                          ])
                        ])
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_43, [
                      _cache[26] || (_cache[26] = _createElementVNode("h3", null, "目标目录配置", -1)),
                      _createElementVNode("div", _hoisted_44, [
                        _createElementVNode("div", _hoisted_45, [
                          _createElementVNode("div", _hoisted_46, [
                            _cache[25] || (_cache[25] = _createElementVNode("span", null, "目标目录列表", -1)),
                            _createElementVNode("span", _hoisted_47, "(" + _toDisplayString(targetExpanded.value.size) + "/" + _toDisplayString(directories.value.length) + ")", 1)
                          ]),
                          _createElementVNode("div", _hoisted_48, [
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(directories.value, (dir) => {
                              return _openBlock(), _createElementBlock("div", {
                                key: dir.path,
                                class: "directory-item"
                              }, [
                                _createElementVNode("div", {
                                  class: "directory-content",
                                  onClick: ($event) => toggleTargetExpanded(dir.path)
                                }, [
                                  _createElementVNode("span", _hoisted_50, _toDisplayString(targetExpanded.value.has(dir.path) ? "▼" : "▶"), 1),
                                  _withDirectives(_createElementVNode("input", {
                                    type: "checkbox",
                                    "onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => config.openlist_target_dirs = $event),
                                    value: dir.path,
                                    class: "directory-checkbox"
                                  }, null, 8, _hoisted_51), [
                                    [_vModelCheckbox, config.openlist_target_dirs]
                                  ]),
                                  _createElementVNode("span", _hoisted_52, _toDisplayString(dir.name), 1)
                                ], 8, _hoisted_49),
                                targetExpanded.value.has(dir.path) && dir.children && dir.children.length > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_53, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(dir.children, (subdir) => {
                                    return _openBlock(), _createElementBlock("div", {
                                      key: subdir.path,
                                      class: "directory-item"
                                    }, [
                                      _createElementVNode("div", {
                                        class: "directory-content",
                                        onClick: ($event) => toggleTargetExpanded(subdir.path)
                                      }, [
                                        _createElementVNode("span", _hoisted_55, _toDisplayString(targetExpanded.value.has(subdir.path) ? "▼" : "▶"), 1),
                                        _withDirectives(_createElementVNode("input", {
                                          type: "checkbox",
                                          "onUpdate:modelValue": _cache[7] || (_cache[7] = ($event) => config.openlist_target_dirs = $event),
                                          value: subdir.path,
                                          class: "directory-checkbox"
                                        }, null, 8, _hoisted_56), [
                                          [_vModelCheckbox, config.openlist_target_dirs]
                                        ]),
                                        _createElementVNode("span", _hoisted_57, _toDisplayString(subdir.name), 1)
                                      ], 8, _hoisted_54),
                                      targetExpanded.value.has(subdir.path) && subdir.children && subdir.children.length > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_58, [
                                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(subdir.children, (deepdir) => {
                                          return _openBlock(), _createElementBlock("div", {
                                            key: deepdir.path,
                                            class: "directory-item"
                                          }, [
                                            _createElementVNode("div", {
                                              class: "directory-content",
                                              onClick: ($event) => toggleTargetExpanded(deepdir.path)
                                            }, [
                                              _createElementVNode("span", _hoisted_60, _toDisplayString(targetExpanded.value.has(deepdir.path) ? "▼" : "▶"), 1),
                                              _withDirectives(_createElementVNode("input", {
                                                type: "checkbox",
                                                "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => config.openlist_target_dirs = $event),
                                                value: deepdir.path,
                                                class: "directory-checkbox"
                                              }, null, 8, _hoisted_61), [
                                                [_vModelCheckbox, config.openlist_target_dirs]
                                              ]),
                                              _createElementVNode("span", _hoisted_62, _toDisplayString(deepdir.name), 1)
                                            ], 8, _hoisted_59),
                                            targetExpanded.value.has(deepdir.path) && deepdir.children && deepdir.children.length > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_63, [
                                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(deepdir.children, (fourdir) => {
                                                return _openBlock(), _createElementBlock("div", {
                                                  key: fourdir.path,
                                                  class: "directory-item"
                                                }, [
                                                  _createElementVNode("div", _hoisted_64, [
                                                    _withDirectives(_createElementVNode("input", {
                                                      type: "checkbox",
                                                      "onUpdate:modelValue": _cache[9] || (_cache[9] = ($event) => config.openlist_target_dirs = $event),
                                                      value: fourdir.path,
                                                      class: "directory-checkbox"
                                                    }, null, 8, _hoisted_65), [
                                                      [_vModelCheckbox, config.openlist_target_dirs]
                                                    ]),
                                                    _createElementVNode("span", _hoisted_66, _toDisplayString(fourdir.name), 1)
                                                  ])
                                                ]);
                                              }), 128))
                                            ])) : _createCommentVNode("", true)
                                          ]);
                                        }), 128))
                                      ])) : _createCommentVNode("", true)
                                    ]);
                                  }), 128))
                                ])) : _createCommentVNode("", true)
                              ]);
                            }), 128))
                          ])
                        ])
                      ])
                    ])
                  ])
                ])
              ])
            ]),
            _createElementVNode("div", _hoisted_67, [
              _cache[32] || (_cache[32] = _createElementVNode("div", { class: "card-header" }, [
                _createElementVNode("h2", null, "定时配置")
              ], -1)),
              _createElementVNode("div", _hoisted_68, [
                _createElementVNode("div", _hoisted_69, [
                  _createElementVNode("div", _hoisted_70, [
                    _createElementVNode("div", _hoisted_71, [
                      _cache[28] || (_cache[28] = _createElementVNode("label", { class: "form-label" }, [
                        _createElementVNode("span", { class: "required-mark" }, "*"),
                        _createTextVNode(" 执行频率 (Cron表达式) ")
                      ], -1)),
                      _withDirectives(_createElementVNode("input", {
                        type: "text",
                        class: "form-control",
                        "onUpdate:modelValue": _cache[10] || (_cache[10] = ($event) => config.cron = $event),
                        placeholder: "默认: 30 3 * * * (每天凌晨3点30分)"
                      }, null, 512), [
                        [_vModelText, config.cron]
                      ]),
                      _cache[29] || (_cache[29] = _createElementVNode("div", { class: "form-hint" }, "Cron表达式格式：秒 分 时 日 月 周，留空则使用默认值", -1))
                    ]),
                    _createElementVNode("div", _hoisted_72, [
                      _createElementVNode("label", _hoisted_73, [
                        _withDirectives(_createElementVNode("input", {
                          type: "checkbox",
                          "onUpdate:modelValue": _cache[11] || (_cache[11] = ($event) => config.enable_wechat_notify = $event),
                          class: "form-checkbox"
                        }, null, 512), [
                          [_vModelCheckbox, config.enable_wechat_notify]
                        ]),
                        _cache[30] || (_cache[30] = _createElementVNode("span", null, "启用企业微信通知", -1))
                      ]),
                      _cache[31] || (_cache[31] = _createElementVNode("div", { class: "form-hint" }, "任务完成后发送企业微信通知，需要MoviePilot已配置企业微信", -1))
                    ])
                  ])
                ])
              ])
            ]),
            _createElementVNode("div", _hoisted_74, [
              _cache[37] || (_cache[37] = _createElementVNode("div", { class: "card-header" }, [
                _createElementVNode("h2", null, "其他配置")
              ], -1)),
              _createElementVNode("div", _hoisted_75, [
                _createElementVNode("div", _hoisted_76, [
                  _createElementVNode("div", _hoisted_77, [
                    _createElementVNode("div", _hoisted_78, [
                      _createElementVNode("label", _hoisted_79, [
                        _withDirectives(_createElementVNode("input", {
                          type: "checkbox",
                          "onUpdate:modelValue": _cache[12] || (_cache[12] = ($event) => config.enable_custom_suffix = $event),
                          class: "form-checkbox"
                        }, null, 512), [
                          [_vModelCheckbox, config.enable_custom_suffix]
                        ]),
                        _cache[33] || (_cache[33] = _createElementVNode("span", null, "启用自定义文件后缀", -1))
                      ]),
                      _cache[34] || (_cache[34] = _createElementVNode("div", { class: "form-hint" }, "除了媒体文件外，是否复制自定义后缀的文件", -1))
                    ]),
                    _createElementVNode("div", _hoisted_80, [
                      _createElementVNode("label", _hoisted_81, [
                        _withDirectives(_createElementVNode("input", {
                          type: "checkbox",
                          "onUpdate:modelValue": _cache[13] || (_cache[13] = ($event) => config.use_moviepilot_config = $event),
                          class: "form-checkbox"
                        }, null, 512), [
                          [_vModelCheckbox, config.use_moviepilot_config]
                        ]),
                        _cache[35] || (_cache[35] = _createElementVNode("span", null, "使用MoviePilot配置", -1))
                      ]),
                      _cache[36] || (_cache[36] = _createElementVNode("div", { class: "form-hint" }, "使用MoviePilot中已配置的OpenList信息（如果存在）", -1))
                    ])
                  ])
                ])
              ])
            ])
          ])
        ])
      ]);
    };
  }
});

const Config_vue_vue_type_style_index_0_scoped_8b43ad42_lang = '';

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-8b43ad42"]]);

export { Config as default };
