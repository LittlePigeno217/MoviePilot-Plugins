import { r as importShared } from "./_virtual___federation_fn_import-j-cuoq0S.js";
import "./preload-helper-GxVotskq.js";
import { t as __plugin_vue_export_helper_default } from "./_plugin-vue_export-helper-BqsoqoUm.js";
var { defineComponent: _defineComponent } = await importShared("vue");
var { createElementVNode: _createElementVNode, vModelCheckbox: _vModelCheckbox, withDirectives: _withDirectives, vModelText: _vModelText, openBlock: _openBlock, createElementBlock: _createElementBlock } = await importShared("vue");
var _hoisted_1 = { class: "plugin-config" };
var _hoisted_2 = { class: "config-form" };
var _hoisted_3 = { class: "form-group" };
var _hoisted_4 = { class: "form-group" };
var _hoisted_5 = { class: "form-group" };
var _hoisted_6 = { class: "form-group" };
var _hoisted_7 = { class: "form-group" };
var _hoisted_8 = { class: "form-group" };
var _hoisted_9 = { class: "form-group" };
var _hoisted_10 = { class: "form-group" };
var { ref } = await importShared("vue");
var Config_default = /* @__PURE__ */ __plugin_vue_export_helper_default(/* @__PURE__ */ _defineComponent({
	__name: "Config",
	props: {
		initialConfig: {
			type: Object,
			default: () => ({})
		},
		api: {
			type: Object,
			default: () => {}
		}
	},
	emits: [
		"save",
		"close",
		"switch"
	],
	setup(__props, { emit: __emit }) {
		const config = ref({ ...__props.initialConfig });
		const emit = __emit;
		function saveConfig() {
			emit("save", config.value);
		}
		function notifySwitch() {
			emit("switch");
		}
		function notifyClose() {
			emit("close");
		}
		return (_ctx, _cache) => {
			return _openBlock(), _createElementBlock("div", _hoisted_1, [
				_cache[16] || (_cache[16] = _createElementVNode("h1", null, "OpenList管理Vue - 配置页面", -1)),
				_cache[17] || (_cache[17] = _createElementVNode("p", null, "这里是OpenList管理Vue插件的配置页面，用于配置插件的各项参数。", -1)),
				_createElementVNode("div", _hoisted_2, [
					_createElementVNode("div", _hoisted_3, [_cache[8] || (_cache[8] = _createElementVNode("label", { for: "enable" }, "启用插件", -1)), _withDirectives(_createElementVNode("input", {
						type: "checkbox",
						id: "enable",
						"onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => config.value.enable = $event)
					}, null, 512), [[_vModelCheckbox, config.value.enable]])]),
					_createElementVNode("div", _hoisted_4, [_cache[9] || (_cache[9] = _createElementVNode("label", { for: "openlist_url" }, "OpenList地址", -1)), _withDirectives(_createElementVNode("input", {
						type: "text",
						id: "openlist_url",
						"onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => config.value.openlist_url = $event),
						placeholder: "http://localhost:5244"
					}, null, 512), [[_vModelText, config.value.openlist_url]])]),
					_createElementVNode("div", _hoisted_5, [_cache[10] || (_cache[10] = _createElementVNode("label", { for: "openlist_token" }, "OpenList令牌", -1)), _withDirectives(_createElementVNode("input", {
						type: "password",
						id: "openlist_token",
						"onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => config.value.openlist_token = $event),
						placeholder: "在OpenList后台获取"
					}, null, 512), [[_vModelText, config.value.openlist_token]])]),
					_createElementVNode("div", _hoisted_6, [_cache[11] || (_cache[11] = _createElementVNode("label", { for: "cron" }, "执行周期", -1)), _withDirectives(_createElementVNode("input", {
						type: "text",
						id: "cron",
						"onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => config.value.cron = $event),
						placeholder: "30 3 * * *"
					}, null, 512), [[_vModelText, config.value.cron]])]),
					_createElementVNode("div", _hoisted_7, [_cache[12] || (_cache[12] = _createElementVNode("label", { for: "directory_pairs" }, "目录配对", -1)), _withDirectives(_createElementVNode("textarea", {
						id: "directory_pairs",
						"onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => config.value.directory_pairs = $event),
						rows: "4",
						placeholder: "源目录1#目标目录1\\n源目录2#目标目录2"
					}, null, 512), [[_vModelText, config.value.directory_pairs]])]),
					_createElementVNode("div", _hoisted_8, [_cache[13] || (_cache[13] = _createElementVNode("label", { for: "enable_custom_suffix" }, "启用自定义后缀", -1)), _withDirectives(_createElementVNode("input", {
						type: "checkbox",
						id: "enable_custom_suffix",
						"onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => config.value.enable_custom_suffix = $event)
					}, null, 512), [[_vModelCheckbox, config.value.enable_custom_suffix]])]),
					_createElementVNode("div", _hoisted_9, [_cache[14] || (_cache[14] = _createElementVNode("label", { for: "use_moviepilot_config" }, "使用MoviePilot的内置OpenList", -1)), _withDirectives(_createElementVNode("input", {
						type: "checkbox",
						id: "use_moviepilot_config",
						"onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => config.value.use_moviepilot_config = $event)
					}, null, 512), [[_vModelCheckbox, config.value.use_moviepilot_config]])]),
					_createElementVNode("div", _hoisted_10, [_cache[15] || (_cache[15] = _createElementVNode("label", { for: "enable_wechat_notify" }, "启用微信通知", -1)), _withDirectives(_createElementVNode("input", {
						type: "checkbox",
						id: "enable_wechat_notify",
						"onUpdate:modelValue": _cache[7] || (_cache[7] = ($event) => config.value.enable_wechat_notify = $event)
					}, null, 512), [[_vModelCheckbox, config.value.enable_wechat_notify]])]),
					_createElementVNode("div", { class: "buttons" }, [
						_createElementVNode("button", {
							onClick: saveConfig,
							class: "primary"
						}, "保存配置"),
						_createElementVNode("button", { onClick: notifySwitch }, "返回详情"),
						_createElementVNode("button", { onClick: notifyClose }, "关闭页面")
					])
				])
			]);
		};
	}
}), [["__scopeId", "data-v-32843fdf"]]);
export { Config_default as default };
