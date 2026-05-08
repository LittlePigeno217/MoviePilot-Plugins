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

const App_vue_vue_type_style_index_0_scoped_2db0d1e7_lang = '';

const _sfc_main = {};
const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');


function _sfc_render(_ctx, _cache) {
  const _component_v_main = _resolveComponent("v-main");
  const _component_v_app = _resolveComponent("v-app");

  return (_openBlock(), _createBlock(_component_v_app, null, {
    default: _withCtx(() => [
      _createVNode(_component_v_main, { class: "dev-shell" }, {
        default: _withCtx(() => [...(_cache[0] || (_cache[0] = [
          _createElementVNode("div", { class: "dev-shell__inner" }, [
            _createElementVNode("h1", null, "Vue-FLZT自动签到"),
            _createElementVNode("p", null, "该前端用于 MoviePilot 插件远程组件开发，请在 MoviePilot 中安装并联调。")
          ], -1)
        ]))]),
        _: 1
      })
    ]),
    _: 1
  }))
}
const App = /*#__PURE__*/_export_sfc(_sfc_main, [['render',_sfc_render],['__scopeId',"data-v-2db0d1e7"]]);

const {createApp} = await importShared('vue');

const {createVuetify} = await importShared('vuetify');

const vuetify = createVuetify();

createApp(App).use(vuetify).mount('#app');
