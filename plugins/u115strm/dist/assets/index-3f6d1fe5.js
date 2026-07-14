import { importShared } from './__federation_fn_import-054b33c3.js';
import AppPage from './__federation_expose_AppPage-0e4cd1a3.js';

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

const {createVNode:_createVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { style: {"padding":"16px"} };

// 独立预览无真实 api，占位空对象

const _sfc_main = {
  __name: 'App',
  setup(__props) {

// 独立预览：展示全屏应用页；真实运行时由 MoviePilot 加载联邦组件
const api = {
  get: async () => ({ success: true, data: {} }),
  post: async () => ({ success: true, data: {} }),
};

return (_ctx, _cache) => {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(AppPage, { api: api })
  ]))
}
}

};

// 独立开发预览入口（MoviePilot 运行时直接加载联邦暴露的 Config/Page/AppPage，不经此文件）
const {createApp} = await importShared('vue');

createApp(_sfc_main).mount('#app');
