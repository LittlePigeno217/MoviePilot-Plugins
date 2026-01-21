import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = { class: "dashboard" };
const _hoisted_2 = { class: "dashboard-content" };
const _hoisted_3 = { class: "dashboard-card" };
const _hoisted_4 = { class: "quick-actions" };
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Dashboard",
  emits: ["navigate"],
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", _hoisted_1, [
        _cache[6] || (_cache[6] = _createElementVNode("div", { class: "dashboard-header" }, [
          _createElementVNode("h2", null, "OpenList Manager Vue"),
          _createElementVNode("p", null, "管理您的媒体列表")
        ], -1)),
        _createElementVNode("div", _hoisted_2, [
          _createElementVNode("div", _hoisted_3, [
            _cache[4] || (_cache[4] = _createElementVNode("h3", null, "快速操作", -1)),
            _createElementVNode("div", _hoisted_4, [
              _createElementVNode("button", {
                onClick: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("navigate", "config")),
                class: "action-btn"
              }, [..._cache[2] || (_cache[2] = [
                _createElementVNode("span", { class: "btn-icon" }, "⚙️", -1),
                _createElementVNode("span", null, "配置", -1)
              ])]),
              _createElementVNode("button", {
                onClick: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("navigate", "page")),
                class: "action-btn"
              }, [..._cache[3] || (_cache[3] = [
                _createElementVNode("span", { class: "btn-icon" }, "📋", -1),
                _createElementVNode("span", null, "列表管理", -1)
              ])])
            ])
          ]),
          _cache[5] || (_cache[5] = _createElementVNode("div", { class: "dashboard-card" }, [
            _createElementVNode("h3", null, "功能说明"),
            _createElementVNode("ul", { class: "feature-list" }, [
              _createElementVNode("li", null, "• 支持多级目录选择"),
              _createElementVNode("li", null, "• 独立的源目录和目标目录配置"),
              _createElementVNode("li", null, "• 企业微信通知"),
              _createElementVNode("li", null, "• 实时媒体计数"),
              _createElementVNode("li", null, "• 复制历史记录")
            ])
          ], -1))
        ])
      ]);
    };
  }
});

const Dashboard_vue_vue_type_style_index_0_scoped_fcf10e56_lang = '';

const Dashboard = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-fcf10e56"]]);

export { Dashboard as default };
