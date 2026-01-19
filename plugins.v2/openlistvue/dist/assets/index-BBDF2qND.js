import { r as importShared } from "./_virtual___federation_fn_import-j-cuoq0S.js";
import "./preload-helper-GxVotskq.js";
import { t as __plugin_vue_export_helper_default } from "./_plugin-vue_export-helper-BqsoqoUm.js";
(function polyfill() {
	const relList = document.createElement("link").relList;
	if (relList && relList.supports && relList.supports("modulepreload")) return;
	for (const link of document.querySelectorAll("link[rel=\"modulepreload\"]")) processPreload(link);
	new MutationObserver((mutations) => {
		for (const mutation of mutations) {
			if (mutation.type !== "childList") continue;
			for (const node of mutation.addedNodes) if (node.tagName === "LINK" && node.rel === "modulepreload") processPreload(node);
		}
	}).observe(document, {
		childList: true,
		subtree: true
	});
	function getFetchOpts(link) {
		const fetchOpts = {};
		if (link.integrity) fetchOpts.integrity = link.integrity;
		if (link.referrerPolicy) fetchOpts.referrerPolicy = link.referrerPolicy;
		if (link.crossOrigin === "use-credentials") fetchOpts.credentials = "include";
		else if (link.crossOrigin === "anonymous") fetchOpts.credentials = "omit";
		else fetchOpts.credentials = "same-origin";
		return fetchOpts;
	}
	function processPreload(link) {
		if (link.ep) return;
		link.ep = true;
		const fetchOpts = getFetchOpts(link);
		fetch(link.href, fetchOpts);
	}
})();
var { defineComponent: _defineComponent$1 } = await importShared("vue");
var { toDisplayString: _toDisplayString, createElementVNode: _createElementVNode$1, createTextVNode: _createTextVNode, Fragment: _Fragment$1, openBlock: _openBlock$1, createElementBlock: _createElementBlock$1 } = await importShared("vue");
var _hoisted_1 = { class: "card" };
var { ref } = await importShared("vue");
var HelloWorld_default = /* @__PURE__ */ __plugin_vue_export_helper_default(/* @__PURE__ */ _defineComponent$1({
	__name: "HelloWorld",
	props: { msg: {} },
	setup(__props) {
		const count = ref(0);
		return (_ctx, _cache) => {
			return _openBlock$1(), _createElementBlock$1(_Fragment$1, null, [
				_createElementVNode$1("h1", null, _toDisplayString(__props.msg), 1),
				_createElementVNode$1("div", _hoisted_1, [_createElementVNode$1("button", {
					type: "button",
					onClick: _cache[0] || (_cache[0] = ($event) => count.value++)
				}, "count is " + _toDisplayString(count.value), 1), _cache[1] || (_cache[1] = _createElementVNode$1("p", null, [
					_createTextVNode(" Edit "),
					_createElementVNode$1("code", null, "components/HelloWorld.vue"),
					_createTextVNode(" to test HMR ")
				], -1))]),
				_cache[2] || (_cache[2] = _createElementVNode$1("p", null, [
					_createTextVNode(" Check out "),
					_createElementVNode$1("a", {
						href: "https://vuejs.org/guide/quick-start.html#local",
						target: "_blank"
					}, "create-vue"),
					_createTextVNode(", the official Vue + Vite starter ")
				], -1)),
				_cache[3] || (_cache[3] = _createElementVNode$1("p", null, [
					_createTextVNode(" Learn more about IDE Support for Vue in the "),
					_createElementVNode$1("a", {
						href: "https://vuejs.org/guide/scaling-up/tooling.html#ide-support",
						target: "_blank"
					}, "Vue Docs Scaling up Guide"),
					_createTextVNode(". ")
				], -1)),
				_cache[4] || (_cache[4] = _createElementVNode$1("p", { class: "read-the-docs" }, "Click on the Vite and Vue logos to learn more", -1))
			], 64);
		};
	}
}), [["__scopeId", "data-v-cc337d8c"]]);
var { defineComponent: _defineComponent } = await importShared("vue");
var { createElementVNode: _createElementVNode, createVNode: _createVNode, Fragment: _Fragment, openBlock: _openBlock, createElementBlock: _createElementBlock } = await importShared("vue");
var App_default = /* @__PURE__ */ __plugin_vue_export_helper_default(/* @__PURE__ */ _defineComponent({
	__name: "App",
	setup(__props) {
		return (_ctx, _cache) => {
			return _openBlock(), _createElementBlock(_Fragment, null, [_cache[0] || (_cache[0] = _createElementVNode("div", null, [_createElementVNode("a", {
				href: "https://vite.dev",
				target: "_blank"
			}, [_createElementVNode("img", {
				src: "/vite.svg",
				class: "logo",
				alt: "Vite logo"
			})]), _createElementVNode("a", {
				href: "https://vuejs.org/",
				target: "_blank"
			}, [_createElementVNode("img", {
				src: "data:image/svg+xml,%3csvg%20xmlns='http://www.w3.org/2000/svg'%20xmlns:xlink='http://www.w3.org/1999/xlink'%20aria-hidden='true'%20role='img'%20class='iconify%20iconify--logos'%20width='37.07'%20height='36'%20preserveAspectRatio='xMidYMid%20meet'%20viewBox='0%200%20256%20198'%3e%3cpath%20fill='%2341B883'%20d='M204.8%200H256L128%20220.8L0%200h97.92L128%2051.2L157.44%200h47.36Z'%3e%3c/path%3e%3cpath%20fill='%2341B883'%20d='m0%200l128%20220.8L256%200h-51.2L128%20132.48L50.56%200H0Z'%3e%3c/path%3e%3cpath%20fill='%2335495E'%20d='M50.56%200L128%20133.12L204.8%200h-47.36L128%2051.2L97.92%200H50.56Z'%3e%3c/path%3e%3c/svg%3e",
				class: "logo vue",
				alt: "Vue logo"
			})])], -1)), _createVNode(HelloWorld_default, { msg: "Vite + Vue" })], 64);
		};
	}
}), [["__scopeId", "data-v-48d00746"]]);
var { createApp } = await importShared("vue");
createApp(App_default).mount("#app");
