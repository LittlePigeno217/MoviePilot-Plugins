import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';
import { a as apiService, d as debounce } from './api-5bacd28b.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {createElementVNode:_createElementVNode$1,toDisplayString:_toDisplayString$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createCommentVNode:_createCommentVNode$1} = await importShared('vue');

const _hoisted_1$1 = { class: "toggle-switch" };
const _hoisted_2$1 = { class: "toggle-container" };
const _hoisted_3$1 = ["checked", "disabled"];
const _hoisted_4$1 = { class: "toggle-content" };
const _hoisted_5$1 = {
  key: 0,
  class: "toggle-label"
};
const _hoisted_6$1 = {
  key: 1,
  class: "toggle-hint"
};
const _sfc_main$1 = /* @__PURE__ */ _defineComponent({
  __name: "ToggleSwitch",
  props: {
    modelValue: {
      type: Boolean,
      default: false
    },
    label: {
      type: String,
      default: ""
    },
    hint: {
      type: String,
      default: ""
    },
    disabled: {
      type: Boolean,
      default: false
    }
  },
  emits: ["update:modelValue", "change"],
  setup(__props, { emit: __emit }) {
    const emit = __emit;
    const handleChange = (event) => {
      const target = event.target;
      const value = target.checked;
      emit("update:modelValue", value);
      emit("change", value);
    };
    return (_ctx, _cache) => {
      return _openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
        _createElementVNode$1("label", _hoisted_2$1, [
          _createElementVNode$1("input", {
            type: "checkbox",
            checked: __props.modelValue,
            onChange: handleChange,
            disabled: __props.disabled
          }, null, 40, _hoisted_3$1),
          _cache[0] || (_cache[0] = _createElementVNode$1("span", { class: "toggle-slider" }, null, -1))
        ]),
        _createElementVNode$1("div", _hoisted_4$1, [
          __props.label ? (_openBlock$1(), _createElementBlock$1("span", _hoisted_5$1, _toDisplayString$1(__props.label), 1)) : _createCommentVNode$1("", true),
          __props.hint ? (_openBlock$1(), _createElementBlock$1("span", _hoisted_6$1, _toDisplayString$1(__props.hint), 1)) : _createCommentVNode$1("", true)
        ])
      ]);
    };
  }
});

const ToggleSwitch_vue_vue_type_style_index_0_scoped_f05ddbc9_lang = '';

const ToggleSwitch = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-f05ddbc9"]]);

const Config_vue_vue_type_style_index_0_scoped_6b95fee3_lang = '';

const {defineComponent,ref} = await importShared('vue');

const _sfc_main = defineComponent({
  name: 'Config',
  components: {
    ToggleSwitch
  },
  props: {
    initialConfig: {
      type: Object,
      default: () => ({})
    },
    api: {
      type: [Object, Function],
      default: () => {}
    }
  },
  emits: ['save', 'close', 'switch'],
  setup(props, { emit }) {
    // 配置数据
    const config = ref({...props.initialConfig});
    const saving = ref(false);
    const saveError = ref('');

    // 初始化API服务
    if (props.api) {
      apiService.setApiInstance(props.api);
    }

    // 保存配置
    const saveConfig = debounce(async () => {
      saving.value = true;
      saveError.value = '';
      try {
          emit('save', config.value);
        } catch (error) {
          saveError.value = `保存失败: ${error.message || '请重试'}`;
          console.error('保存配置失败:', error);
        } finally {
          saving.value = false;
        }
    }, 500);

    // 通知主应用切换到详情页面
    function notifySwitch() {
      emit('switch');
    }

    // 通知主应用关闭当前页面
    function notifyClose() {
      emit('close');
    }

    // 清除缓存
    const clearingCache = ref(false);
    const clearCacheMessage = ref('');
    const showClearCacheDialog = ref(false);

    // 显示确认对话框
    const openClearCacheDialog = () => {
      clearCacheMessage.value = '';
      showClearCacheDialog.value = true;
    };

    // 确认清除缓存
    const confirmClearCache = async () => {
      showClearCacheDialog.value = false;
      
      try {
          // 开始清除操作
          clearingCache.value = true;
          
          // 调用 API 清除缓存
          const response = await apiService.clearPluginCache();
          if (response && !response.error) {
            clearCacheMessage.value = '缓存清除成功！';
            // 重新获取配置
            const newConfig = await apiService.getConfig();
            if (newConfig) {
              config.value = {...newConfig};
            }
          } else {
            clearCacheMessage.value = `清除失败: ${response?.message || '请重试'}`;
          }
        } catch (error) {
          clearCacheMessage.value = `清除失败: ${error.message || '请重试'}`;
          console.error('清除缓存失败:', error);
        } finally {
          clearingCache.value = false;
          // 3秒后清除消息
          setTimeout(() => {
            clearCacheMessage.value = '';
          }, 3000);
        }
    };

    // 取消清除缓存
    const cancelClearCache = () => {
      showClearCacheDialog.value = false;
    };

    return {
      config,
      saving,
      saveError,
      saveConfig,
      notifySwitch,
      notifyClose,
      clearingCache,
      clearCacheMessage,
      showClearCacheDialog,
      openClearCacheDialog,
      confirmClearCache,
      cancelClearCache
    }
  }
});

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,normalizeClass:_normalizeClass,resolveComponent:_resolveComponent,createVNode:_createVNode,vModelText:_vModelText,withDirectives:_withDirectives} = await importShared('vue');


const _hoisted_1 = { class: "config-container" };
const _hoisted_2 = { class: "config-header" };
const _hoisted_3 = { class: "header-actions" };
const _hoisted_4 = ["disabled"];
const _hoisted_5 = ["disabled"];
const _hoisted_6 = {
  key: 0,
  class: "error-message"
};
const _hoisted_7 = { class: "config-form" };
const _hoisted_8 = { class: "config-section" };
const _hoisted_9 = { class: "toggle-grid" };
const _hoisted_10 = { class: "toggle-item" };
const _hoisted_11 = { class: "toggle-item" };
const _hoisted_12 = { class: "toggle-item" };
const _hoisted_13 = { class: "toggle-item" };
const _hoisted_14 = { class: "config-section" };
const _hoisted_15 = { class: "form-group" };
const _hoisted_16 = {
  key: 0,
  class: "config-section"
};
const _hoisted_17 = { class: "form-grid" };
const _hoisted_18 = { class: "form-group" };
const _hoisted_19 = { class: "form-group" };
const _hoisted_20 = { class: "config-section" };
const _hoisted_21 = { class: "form-group" };
const _hoisted_22 = {
  key: 2,
  class: "modal-overlay"
};
const _hoisted_23 = { class: "modal-content" };
const _hoisted_24 = { class: "modal-footer" };
const _hoisted_25 = ["disabled"];

function _sfc_render(_ctx, _cache, $props, $setup, $data, $options) {
  const _component_ToggleSwitch = _resolveComponent("ToggleSwitch");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[14] || (_cache[14] = _createElementVNode("h2", null, "OpenList管理Vue - 配置", -1)),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("button", {
          onClick: _cache[0] || (_cache[0] = (...args) => (_ctx.saveConfig && _ctx.saveConfig(...args))),
          class: "btn btn-primary",
          disabled: _ctx.saving
        }, _toDisplayString(_ctx.saving ? '保存中...' : '保存配置'), 9, _hoisted_4),
        _createElementVNode("button", {
          onClick: _cache[1] || (_cache[1] = (...args) => (_ctx.notifySwitch && _ctx.notifySwitch(...args))),
          class: "btn btn-secondary"
        }, " 切换到详情页面 "),
        _createElementVNode("button", {
          onClick: _cache[2] || (_cache[2] = (...args) => (_ctx.openClearCacheDialog && _ctx.openClearCacheDialog(...args))),
          class: "btn btn-warning",
          disabled: _ctx.clearingCache
        }, _toDisplayString(_ctx.clearingCache ? '清除中...' : '清除缓存'), 9, _hoisted_5),
        _createElementVNode("button", {
          onClick: _cache[3] || (_cache[3] = (...args) => (_ctx.notifyClose && _ctx.notifyClose(...args))),
          class: "btn btn-secondary"
        }, " 关闭页面 ")
      ])
    ]),
    (_ctx.saveError)
      ? (_openBlock(), _createElementBlock("div", _hoisted_6, _toDisplayString(_ctx.saveError), 1))
      : _createCommentVNode("", true),
    (_ctx.clearCacheMessage)
      ? (_openBlock(), _createElementBlock("div", {
          key: 1,
          class: _normalizeClass(["message-box", _ctx.clearCacheMessage.includes('成功') ? 'success-message' : 'error-message'])
        }, _toDisplayString(_ctx.clearCacheMessage), 3))
      : _createCommentVNode("", true),
    _createElementVNode("div", _hoisted_7, [
      _createElementVNode("section", _hoisted_8, [
        _cache[15] || (_cache[15] = _createElementVNode("h3", { class: "section-title" }, "基本设置", -1)),
        _createElementVNode("div", _hoisted_9, [
          _createElementVNode("div", _hoisted_10, [
            _createVNode(_component_ToggleSwitch, {
              modelValue: _ctx.config.enabled,
              "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((_ctx.config.enabled) = $event)),
              label: "启动插件"
            }, null, 8, ["modelValue"])
          ]),
          _createElementVNode("div", _hoisted_11, [
            _createVNode(_component_ToggleSwitch, {
              modelValue: _ctx.config.enable_custom_suffix,
              "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((_ctx.config.enable_custom_suffix) = $event)),
              label: "刮削文件",
              hint: "额外复制字幕、元数据、封面图文件"
            }, null, 8, ["modelValue"])
          ]),
          _createElementVNode("div", _hoisted_12, [
            _createVNode(_component_ToggleSwitch, {
              modelValue: _ctx.config.use_moviepilot_config,
              "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((_ctx.config.use_moviepilot_config) = $event)),
              label: "使用内置OpenList",
              hint: "使用MoviePilot内置的OpenList实例"
            }, null, 8, ["modelValue"])
          ]),
          _createElementVNode("div", _hoisted_13, [
            _createVNode(_component_ToggleSwitch, {
              modelValue: _ctx.config.enable_wechat_notify,
              "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((_ctx.config.enable_wechat_notify) = $event)),
              label: "通知提醒",
              hint: "复制任务时发送企业微信卡片通知"
            }, null, 8, ["modelValue"])
          ])
        ])
      ]),
      _createElementVNode("section", _hoisted_14, [
        _cache[18] || (_cache[18] = _createElementVNode("h3", { class: "section-title" }, "执行周期", -1)),
        _createElementVNode("div", _hoisted_15, [
          _cache[16] || (_cache[16] = _createElementVNode("label", { for: "cron" }, "Cron表达式", -1)),
          _withDirectives(_createElementVNode("input", {
            type: "text",
            id: "cron",
            "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((_ctx.config.cron) = $event)),
            placeholder: "0 2 * * *",
            class: "form-input"
          }, null, 512), [
            [_vModelText, _ctx.config.cron]
          ]),
          _cache[17] || (_cache[17] = _createElementVNode("span", { class: "form-hint" }, "默认每天凌晨2点执行复制任务", -1))
        ])
      ]),
      (!_ctx.config.use_moviepilot_config)
        ? (_openBlock(), _createElementBlock("section", _hoisted_16, [
            _cache[23] || (_cache[23] = _createElementVNode("h3", { class: "section-title" }, "OpenList配置", -1)),
            _createElementVNode("div", _hoisted_17, [
              _createElementVNode("div", _hoisted_18, [
                _cache[19] || (_cache[19] = _createElementVNode("label", { for: "openlist_url" }, "OpenList地址", -1)),
                _withDirectives(_createElementVNode("input", {
                  type: "text",
                  id: "openlist_url",
                  "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((_ctx.config.openlist_url) = $event)),
                  placeholder: "http://localhost:5244",
                  class: "form-input"
                }, null, 512), [
                  [_vModelText, _ctx.config.openlist_url]
                ]),
                _cache[20] || (_cache[20] = _createElementVNode("span", { class: "form-hint" }, "请输入完整的OpenList服务地址", -1))
              ]),
              _createElementVNode("div", _hoisted_19, [
                _cache[21] || (_cache[21] = _createElementVNode("label", { for: "openlist_token" }, "OpenList令牌", -1)),
                _withDirectives(_createElementVNode("input", {
                  type: "password",
                  id: "openlist_token",
                  "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((_ctx.config.openlist_token) = $event)),
                  placeholder: "在OpenList后台获取",
                  class: "form-input"
                }, null, 512), [
                  [_vModelText, _ctx.config.openlist_token]
                ]),
                _cache[22] || (_cache[22] = _createElementVNode("span", { class: "form-hint" }, "在OpenList管理后台的'设置'-'全局'中获取令牌", -1))
              ])
            ])
          ]))
        : _createCommentVNode("", true),
      _createElementVNode("section", _hoisted_20, [
        _cache[26] || (_cache[26] = _createElementVNode("h3", { class: "section-title" }, "目录配对设置", -1)),
        _createElementVNode("div", _hoisted_21, [
          _cache[24] || (_cache[24] = _createElementVNode("label", { for: "directory_pairs" }, "目录配对", -1)),
          _withDirectives(_createElementVNode("textarea", {
            id: "directory_pairs",
            "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((_ctx.config.directory_pairs) = $event)),
            placeholder: "源目录1#目标目录1\\n源目录2#目标目录2",
            class: "form-textarea",
            rows: "4"
          }, null, 512), [
            [_vModelText, _ctx.config.directory_pairs]
          ]),
          _cache[25] || (_cache[25] = _createElementVNode("span", { class: "form-hint" }, "每行一组配对，使用#分隔源目录和目标目录", -1))
        ])
      ])
    ]),
    (_ctx.showClearCacheDialog)
      ? (_openBlock(), _createElementBlock("div", _hoisted_22, [
          _createElementVNode("div", _hoisted_23, [
            _cache[27] || (_cache[27] = _createElementVNode("div", { class: "modal-header" }, [
              _createElementVNode("h3", null, "确认清除缓存")
            ], -1)),
            _cache[28] || (_cache[28] = _createElementVNode("div", { class: "modal-body" }, [
              _createElementVNode("p", null, "是否确认清除插件缓存和文件标识？此操作将重置所有复制记录。")
            ], -1)),
            _createElementVNode("div", _hoisted_24, [
              _createElementVNode("button", {
                onClick: _cache[12] || (_cache[12] = (...args) => (_ctx.cancelClearCache && _ctx.cancelClearCache(...args))),
                class: "btn btn-secondary"
              }, "取消"),
              _createElementVNode("button", {
                onClick: _cache[13] || (_cache[13] = (...args) => (_ctx.confirmClearCache && _ctx.confirmClearCache(...args))),
                class: "btn btn-warning",
                disabled: _ctx.clearingCache
              }, _toDisplayString(_ctx.clearingCache ? '清除中...' : '确认'), 9, _hoisted_25)
            ])
          ])
        ]))
      : _createCommentVNode("", true)
  ]))
}
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['render',_sfc_render],['__scopeId',"data-v-6b95fee3"]]);

export { Config as default };
