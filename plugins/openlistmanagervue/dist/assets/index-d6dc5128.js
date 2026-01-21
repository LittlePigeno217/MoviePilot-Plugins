import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

true&&(function polyfill() {
    const relList = document.createElement('link').relList;
    if (relList && relList.supports && relList.supports('modulepreload')) {
        return;
    }
    for (const link of document.querySelectorAll('link[rel="modulepreload"]')) {
        processPreload(link);
    }
    new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type !== 'childList') {
                continue;
            }
            for (const node of mutation.addedNodes) {
                if (node.tagName === 'LINK' && node.rel === 'modulepreload')
                    processPreload(node);
            }
        }
    }).observe(document, { childList: true, subtree: true });
    function getFetchOpts(link) {
        const fetchOpts = {};
        if (link.integrity)
            fetchOpts.integrity = link.integrity;
        if (link.referrerPolicy)
            fetchOpts.referrerPolicy = link.referrerPolicy;
        if (link.crossOrigin === 'use-credentials')
            fetchOpts.credentials = 'include';
        else if (link.crossOrigin === 'anonymous')
            fetchOpts.credentials = 'omit';
        else
            fetchOpts.credentials = 'same-origin';
        return fetchOpts;
    }
    function processPreload(link) {
        if (link.ep)
            // ep marker = processed
            return;
        link.ep = true;
        // prepopulate the load record
        const fetchOpts = getFetchOpts(link);
        fetch(link.href, fetchOpts);
    }
}());

const style = '';

const {defineComponent:_defineComponent} = await importShared('vue');

const {createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = { class: "app-container" };
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "App",
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", _hoisted_1, [..._cache[0] || (_cache[0] = [
        _createElementVNode("h1", null, "OpenListManagerVue", -1),
        _createElementVNode("div", { class: "app-content" }, [
          _createElementVNode("p", null, "这是一个MoviePilot插件，用于管理OpenList多目录间的文件复制。"),
          _createElementVNode("p", null, "请通过MoviePilot插件页面访问此插件的功能。")
        ], -1)
      ])]);
    };
  }
});

const App_vue_vue_type_style_index_0_scoped_2ac44ced_lang = '';

const App = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-2ac44ced"]]);

const {createApp} = await importShared('vue');
createApp(App).mount("#app");
