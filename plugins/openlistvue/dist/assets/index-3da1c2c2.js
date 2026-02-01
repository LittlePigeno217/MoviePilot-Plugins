import { importShared } from './__federation_fn_import-054b33c3.js';
import Page from './__federation_expose_Page-e7d53dbe.js';
import Config from './__federation_expose_Config-65804c1b.js';
import Dashboard from './__federation_expose_Dashboard-00dd73e3.js';

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

const {defineComponent:_defineComponent} = await importShared('vue');

const {createElementVNode:_createElementVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = { class: "app-container" };
const _hoisted_2 = { class: "app-header" };
const _hoisted_3 = { class: "app-nav" };
const _hoisted_4 = { class: "app-main" };
const {ref} = await importShared('vue');

const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "App",
  setup(__props) {
    const activeComponent = ref("page");
    const mockApi = {
      get: async (url) => {
        if (url === "/status") {
          return {
            data: {
              status: "idle",
              progress: 0,
              message: "",
              last_run: (/* @__PURE__ */ new Date()).toISOString(),
              total_files: 100,
              copied_files: 50,
              skipped_files: 10,
              file_identifier_stats: {
                total: 100,
                completed: 50,
                copying: 50
              }
            }
          };
        } else if (url === "/config") {
          return {
            data: {
              enabled: true,
              openlist_url: "http://localhost:5244",
              openlist_token: "mock-token",
              directory_pairs: "源目录1#目标目录1\n源目录2#目标目录2",
              enable_custom_suffix: true,
              cron: "0 2 * * *",
              use_moviepilot_config: false,
              enable_wechat_notify: true
            }
          };
        } else if (url === "/combined") {
          return {
            data: {
              config: {
                enabled: true,
                openlist_url: "http://localhost:5244",
                openlist_token: "mock-token",
                directory_pairs: "源目录1#目标目录1\n源目录2#目标目录2",
                enable_custom_suffix: true,
                cron: "0 2 * * *",
                use_moviepilot_config: false,
                enable_wechat_notify: true
              },
              status: {
                enabled: true,
                cron: "0 2 * * *",
                next_run_time: "2024-01-01 02:00:00",
                task_status: {
                  status: "idle",
                  progress: 0,
                  message: "",
                  last_run: (/* @__PURE__ */ new Date()).toISOString(),
                  total_files: 100,
                  copied_files: 50,
                  skipped_files: 10
                },
                copied_files_count: 100,
                target_files_count: 80,
                file_identifier_stats: {
                  total: 100,
                  completed: 50,
                  copying: 50
                }
              },
              auth: {
                connected: true,
                message: "连接成功",
                status: "通过",
                timestamp: (/* @__PURE__ */ new Date()).toISOString()
              }
            }
          };
        }
        return { data: {} };
      },
      post: async (url) => {
        if (url === "/run") {
          return { success: true };
        } else if (url === "/clear_cache") {
          return {
            data: {
              message: "缓存和文件标识已成功清除"
            }
          };
        }
        return { success: false };
      }
    };
    const mockConfig = {
      enabled: true,
      openlist_url: "http://localhost:5244",
      openlist_token: "mock-token",
      directory_pairs: "源目录1#目标目录1\n源目录2#目标目录2",
      enable_custom_suffix: true,
      cron: "0 2 * * *",
      use_moviepilot_config: false,
      enable_wechat_notify: true
    };
    const switchComponent = (component) => {
      activeComponent.value = component;
    };
    const handleSaveConfig = (config) => {
      console.log("保存配置:", config);
      alert("配置已保存");
    };
    const handleAction = () => {
      console.log("执行动作");
    };
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", _hoisted_1, [
        _createElementVNode("header", _hoisted_2, [
          _cache[7] || (_cache[7] = _createElementVNode("h1", null, "OpenList管理Vue - 本地开发测试", -1)),
          _createElementVNode("nav", _hoisted_3, [
            _createElementVNode("button", {
              onClick: _cache[0] || (_cache[0] = ($event) => switchComponent("page")),
              class: _normalizeClass({ active: activeComponent.value === "page" })
            }, " 详情页面 ", 2),
            _createElementVNode("button", {
              onClick: _cache[1] || (_cache[1] = ($event) => switchComponent("config")),
              class: _normalizeClass({ active: activeComponent.value === "config" })
            }, " 配置页面 ", 2),
            _createElementVNode("button", {
              onClick: _cache[2] || (_cache[2] = ($event) => switchComponent("dashboard")),
              class: _normalizeClass({ active: activeComponent.value === "dashboard" })
            }, " 仪表板 ", 2)
          ])
        ]),
        _createElementVNode("main", _hoisted_4, [
          activeComponent.value === "page" ? (_openBlock(), _createBlock(Page, {
            key: 0,
            api: mockApi,
            onAction: handleAction,
            onSwitch: _cache[3] || (_cache[3] = ($event) => switchComponent("config")),
            onClose: _cache[4] || (_cache[4] = ($event) => console.log("关闭页面"))
          })) : _createCommentVNode("", true),
          activeComponent.value === "config" ? (_openBlock(), _createBlock(Config, {
            key: 1,
            "initial-config": mockConfig,
            api: mockApi,
            onSave: handleSaveConfig,
            onSwitch: _cache[5] || (_cache[5] = ($event) => switchComponent("page")),
            onClose: _cache[6] || (_cache[6] = ($event) => console.log("关闭页面"))
          })) : _createCommentVNode("", true),
          activeComponent.value === "dashboard" ? (_openBlock(), _createBlock(Dashboard, {
            key: 2,
            config: mockConfig,
            "allow-refresh": true
          })) : _createCommentVNode("", true)
        ]),
        _cache[8] || (_cache[8] = _createElementVNode("footer", { class: "app-footer" }, [
          _createElementVNode("p", null, "OpenList管理Vue v1.2.0 - 作者: LittlePigeno")
        ], -1))
      ]);
    };
  }
});

const App_vue_vue_type_style_index_0_lang = '';

const {createApp} = await importShared('vue');
createApp(_sfc_main).mount("#app");
