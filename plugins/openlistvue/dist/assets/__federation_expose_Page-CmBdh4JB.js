import { r as importShared } from "./_virtual___federation_fn_import-j-cuoq0S.js";
import "./preload-helper-GxVotskq.js";
import { t as __plugin_vue_export_helper_default } from "./_plugin-vue_export-helper-BqsoqoUm.js";
var { defineComponent: _defineComponent } = await importShared("vue");
var { createElementVNode: _createElementVNode, openBlock: _openBlock, createElementBlock: _createElementBlock } = await importShared("vue");
var _hoisted_1 = { class: "plugin-page" };
var Page_default = /* @__PURE__ */ __plugin_vue_export_helper_default(/* @__PURE__ */ _defineComponent({
	__name: "Page",
	props: { api: {
		type: Object,
		default: () => {}
	} },
	emits: [
		"action",
		"switch",
		"close"
	],
	setup(__props, { emit: __emit }) {
		const emit = __emit;
		function notifyRefresh() {
			emit("action");
		}
		function notifySwitch() {
			emit("switch");
		}
		function notifyClose() {
			emit("close");
		}
		return (_ctx, _cache) => {
			return _openBlock(), _createElementBlock("div", _hoisted_1, [
				_cache[0] || (_cache[0] = _createElementVNode("h1", null, "OpenList管理Vue - 详情页面", -1)),
				_cache[1] || (_cache[1] = _createElementVNode("p", null, "这里是OpenList管理Vue插件的详情页面，用于展示插件的运行状态和统计信息。", -1)),
				_createElementVNode("div", { class: "buttons" }, [
					_createElementVNode("button", { onClick: notifyRefresh }, "刷新数据"),
					_createElementVNode("button", { onClick: notifySwitch }, "配置插件"),
					_createElementVNode("button", { onClick: notifyClose }, "关闭页面")
				])
			]);
		};
	}
}), [["__scopeId", "data-v-05cb774c"]]);
export { Page_default as default };
