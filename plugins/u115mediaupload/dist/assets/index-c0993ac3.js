import { importShared } from './__federation_fn_import-054b33c3.js';
import Config from './__federation_expose_Config-fe12c113.js';
import Page from './__federation_expose_Page-7c7c88d5.js';
import AppPage from './__federation_expose_AppPage-a711497f.js';
import './PathMappingEditor-b57145b1.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-75e59c87.js';

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

const App_vue_vue_type_style_index_0_scoped_dcc6b7e4_lang = '';

const {createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,resolveDynamicComponent:_resolveDynamicComponent,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "u115-shell__top" };

const {computed,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'App',
  setup(__props) {

const activeTab = ref('console');

const tabs = [
  { value: 'console', label: '控制台' },
  { value: 'config', label: '配置' },
  { value: 'page', label: '状态' },
];

const tabComponent = computed(() => {
  if (activeTab.value === 'config') return Config
  if (activeTab.value === 'page') return Page
  return AppPage
});

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_main = _resolveComponent("v-main");
  const _component_v_app = _resolveComponent("v-app");

  return (_openBlock(), _createBlock(_component_v_app, null, {
    default: _withCtx(() => [
      _createVNode(_component_v_main, { class: "u115-shell" }, {
        default: _withCtx(() => [
          _createElementVNode("div", _hoisted_1, [
            _cache[1] || (_cache[1] = _createElementVNode("div", null, [
              _createElementVNode("div", { class: "u115-shell__title" }, "115媒体上传"),
              _createElementVNode("div", { class: "u115-shell__subtitle" }, "全量、增量、刮削和秒传控制台")
            ], -1)),
            _createVNode(_component_v_btn_toggle, {
              modelValue: activeTab.value,
              "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((activeTab).value = $event)),
              mandatory: "",
              variant: "tonal",
              density: "comfortable"
            }, {
              default: _withCtx(() => [
                (_openBlock(), _createElementBlock(_Fragment, null, _renderList(tabs, (tab) => {
                  return _createVNode(_component_v_btn, {
                    key: tab.value,
                    value: tab.value
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(tab.label), 1)
                    ]),
                    _: 2
                  }, 1032, ["value"])
                }), 64))
              ]),
              _: 1
            }, 8, ["modelValue"])
          ]),
          (_openBlock(), _createBlock(_resolveDynamicComponent(tabComponent.value)))
        ]),
        _: 1
      })
    ]),
    _: 1
  }))
}
}

};
const App = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-dcc6b7e4"]]);

const {createApp} = await importShared('vue');

const {createVuetify} = await importShared('vuetify');

const vuetify = createVuetify();

createApp(App).use(vuetify).mount('#app');
