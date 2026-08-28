import { importShared } from './__federation_fn_import-054b33c3.js';

const AppBar_vue_vue_type_style_index_0_scoped_17d09ef4_lang = '';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,resolveComponent:_resolveComponent,createBlock:_createBlock,createVNode:_createVNode} = await importShared('vue');


const _hoisted_1 = { class: "bar" };
const _hoisted_2 = { class: "bar__names" };
const _hoisted_3 = { class: "bar__view ck-eyebrow" };
const _hoisted_4 = { class: "bar__tools" };


const _sfc_main = {
  __name: 'AppBar',
  props: {
  view: { type: String, default: '' },
  state: { type: String, default: '' },
  tone: { type: String, default: 'idle' },
  showSwitch: { type: Boolean, default: true },
  showRefresh: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
},
  emits: ['switch', 'close', 'refresh'],
  setup(__props, { emit: __emit }) {

/**
 * 插件自己的标题栏。MoviePilot 的 vue 渲染分支不提供标题和关闭按钮
 * （VCardText 用了 pa-0），所以这些控件必须由插件提供。
 */

const emit = __emit;

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");

  return (_openBlock(), _createElementBlock("header", _hoisted_1, [
    _cache[5] || (_cache[5] = _createElementVNode("span", {
      class: "bar__mark",
      "aria-hidden": "true"
    }, "签", -1)),
    _createElementVNode("span", _hoisted_2, [
      _cache[3] || (_cache[3] = _createElementVNode("span", { class: "bar__name" }, "自用签到", -1)),
      _createElementVNode("span", _hoisted_3, _toDisplayString(__props.view), 1)
    ]),
    (__props.state)
      ? (_openBlock(), _createElementBlock("span", {
          key: 0,
          class: _normalizeClass(["bar__state", `bar__state--${__props.tone}`])
        }, [
          _cache[4] || (_cache[4] = _createElementVNode("span", {
            class: "bar__dot",
            "aria-hidden": "true"
          }, null, -1)),
          _createTextVNode(" " + _toDisplayString(__props.state), 1)
        ], 2))
      : _createCommentVNode("", true),
    _createElementVNode("span", _hoisted_4, [
      (__props.showRefresh)
        ? (_openBlock(), _createBlock(_component_v_btn, {
            key: 0,
            icon: "mdi-refresh",
            variant: "text",
            size: "small",
            loading: __props.busy,
            "aria-label": "刷新状态",
            onClick: _cache[0] || (_cache[0] = $event => (emit('refresh')))
          }, null, 8, ["loading"]))
        : _createCommentVNode("", true),
      (__props.showSwitch)
        ? (_openBlock(), _createBlock(_component_v_btn, {
            key: 1,
            icon: "mdi-swap-horizontal",
            variant: "text",
            size: "small",
            "aria-label": __props.view === '台账' ? '前往设置' : '前往台账',
            onClick: _cache[1] || (_cache[1] = $event => (emit('switch')))
          }, null, 8, ["aria-label"]))
        : _createCommentVNode("", true),
      _createVNode(_component_v_btn, {
        icon: "mdi-close",
        variant: "text",
        size: "small",
        "aria-label": "关闭",
        onClick: _cache[2] || (_cache[2] = $event => (emit('close')))
      })
    ])
  ]))
}
}

};
const AppBar = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-17d09ef4"]]);

// 自用签到工具 —— 前端共享模块
// 站点元数据、配置规范化与校验、请求封装。与后端 API 契约保持一致。

const PLUGIN_ID = 'Checkin';

// 站点元数据：key、显示名、登录方式、卡面缩写
const SITE_META = {
  flzt: { key: 'flzt', title: 'FLZT', mode: '账号密码', badge: 'FZ' },
  right_forum: { key: 'right_forum', title: '恩山无线论坛', mode: 'Cookie', badge: 'ES' },
  ypojie: { key: 'ypojie', title: '易破解', mode: '账号密码', badge: 'YP' },
};

const SITE_KEYS = Object.keys(SITE_META);

const DEFAULT_CONFIG = {
  enabled: false,
  notify: true,
  cron: '10 8 * * *',
  timeout: 10,
  retry_count: 3,
  sites: {
    flzt: { enabled: false, use_proxy: false, email: '', password: '' },
    right_forum: { enabled: false, use_proxy: false, cookie: '' },
    ypojie: { enabled: false, use_proxy: false, email: '', password: '' },
  },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value || {}))
}

// 把后端返回补齐为完整结构，缺字段不会让 v-model 绑定炸掉
function normalizeConfig(value = {}) {
  const config = { ...clone(DEFAULT_CONFIG), ...clone(value) };
  config.sites = {};
  for (const key of SITE_KEYS) {
    config.sites[key] = { ...DEFAULT_CONFIG.sites[key], ...(value.sites?.[key] || {}) };
  }
  return config
}

// 兼容 MoviePilot 传输层可能包裹的 { data: ... } 外壳
function unwrapTransport(response) {
  if (
    response
    && typeof response === 'object'
    && Object.prototype.hasOwnProperty.call(response, 'data')
    && !Object.prototype.hasOwnProperty.call(response, 'success')
    && !Object.prototype.hasOwnProperty.call(response, 'message')
  ) {
    return response.data
  }
  return response
}

function unwrapData(response) {
  const body = unwrapTransport(response);
  if (body && typeof body === 'object' && Object.prototype.hasOwnProperty.call(body, 'data')) {
    return body.data ?? {}
  }
  return body ?? {}
}

function unwrapResult(response) {
  const body = unwrapTransport(response);
  if (!body || typeof body !== 'object') return { success: true, message: '', data: body }
  if (
    Object.prototype.hasOwnProperty.call(body, 'success')
    || Object.prototype.hasOwnProperty.call(body, 'message')
    || Object.prototype.hasOwnProperty.call(body, 'data')
  ) {
    return { success: body.success !== false, message: body.message || '', data: body.data }
  }
  return { success: true, message: '', data: body }
}

async function pluginGet(api, path) {
  if (!api?.get) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  return unwrapData(await api.get(`plugin/${PLUGIN_ID}${path}`))
}

async function pluginPost(api, path, payload = {}) {
  if (!api?.post) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  return unwrapResult(await api.post(`plugin/${PLUGIN_ID}${path}`, payload))
}

// 保存前校验，和后端 validate_config 的规则对齐
function validateConfig(config) {
  const errors = [];
  const sites = config.sites || {};

  for (const key of ['flzt', 'ypojie']) {
    const site = sites[key];
    if (site?.enabled && (!site.email || !site.password)) {
      errors.push(`${SITE_META[key].title} 已启用但账号或密码未填写`);
    }
  }

  const forum = sites.right_forum;
  if (forum?.enabled) {
    const cookie = String(forum.cookie || '').trim();
    if (!cookie) errors.push(`${SITE_META.right_forum.title} 已启用但 Cookie 未填写`);
    else if (!cookie.includes('=') || cookie.length < 20) errors.push(`${SITE_META.right_forum.title} Cookie 格式异常`);
  }

  return errors
}

/**
 * MoviePilot 通过 provide('moviepilot:toast') 把宿主的消息条交给远程组件。
 * 宿主缺席时（独立联调）退回本地提示条。
 */
function useHostNotice(injected, local) {
  const speak = (text, kind = 'info') => {
    const message = String(text || '').trim();
    if (!message) return
    const host = injected?.value ?? injected;
    const method = host?.[kind] || host?.info;
    if (typeof method === 'function') {
      method.call(host, message);
      return
    }
    if (typeof host === 'function') {
      host(message, kind);
      return
    }
    local(message, kind);
  };
  return {
    info: text => speak(text, 'info'),
    success: text => speak(text, 'success'),
    error: text => speak(text, 'error'),
    warning: text => speak(text, 'warning'),
    say: speak,
  }
}

const kit = '';

export { AppBar as A, SITE_META as S, _export_sfc as _, pluginPost as a, clone as c, normalizeConfig as n, pluginGet as p, useHostNotice as u, validateConfig as v };
