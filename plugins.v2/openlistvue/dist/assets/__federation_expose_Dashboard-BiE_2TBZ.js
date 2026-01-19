import { r as importShared } from "./_virtual___federation_fn_import-j-cuoq0S.js";
import "./preload-helper-GxVotskq.js";
import { t as __plugin_vue_export_helper_default } from "./_plugin-vue_export-helper-BqsoqoUm.js";
var { defineComponent: _defineComponent } = await importShared("vue");
var { toDisplayString: _toDisplayString, createElementVNode: _createElementVNode, openBlock: _openBlock, createElementBlock: _createElementBlock, createCommentVNode: _createCommentVNode, createStaticVNode: _createStaticVNode } = await importShared("vue");
var _hoisted_1 = { class: "dashboard-widget" };
var _hoisted_2 = { class: "dashboard-card" };
var _hoisted_3 = {
	key: 0,
	class: "refresh-button"
};
var Dashboard_default = /* @__PURE__ */ __plugin_vue_export_helper_default(/* @__PURE__ */ _defineComponent({
	__name: "Dashboard",
	props: {
		config: {
			type: Object,
			default: () => ({})
		},
		allowRefresh: {
			type: Boolean,
			default: true
		}
	},
	setup(__props) {
		return (_ctx, _cache) => {
			return _openBlock(), _createElementBlock("div", _hoisted_1, [_createElementVNode("div", _hoisted_2, [
				_createElementVNode("h3", null, _toDisplayString(__props.config.title || "OpenList管理"), 1),
				_cache[1] || (_cache[1] = _createStaticVNode("<div class=\"dashboard-content\" data-v-a7235b51><p data-v-a7235b51>这是OpenList管理Vue插件的仪表板组件，用于在MoviePilot仪表板上显示插件的关键信息和状态。</p><div class=\"stats\" data-v-a7235b51><div class=\"stat-item\" data-v-a7235b51><span class=\"stat-label\" data-v-a7235b51>插件状态</span><span class=\"stat-value\" data-v-a7235b51>已启用</span></div><div class=\"stat-item\" data-v-a7235b51><span class=\"stat-label\" data-v-a7235b51>目录配对</span><span class=\"stat-value\" data-v-a7235b51>2</span></div><div class=\"stat-item\" data-v-a7235b51><span class=\"stat-label\" data-v-a7235b51>复制任务</span><span class=\"stat-value\" data-v-a7235b51>0</span></div></div></div>", 1)),
				__props.allowRefresh ? (_openBlock(), _createElementBlock("div", _hoisted_3, [..._cache[0] || (_cache[0] = [_createElementVNode("button", null, "刷新数据", -1)])])) : _createCommentVNode("", true)
			])]);
		};
	}
}), [["__scopeId", "data-v-a7235b51"]]);
export { Dashboard_default as default };
