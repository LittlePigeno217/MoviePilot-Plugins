import { importShared } from './__federation_fn_import-054b33c3.js';

const AppBar_vue_vue_type_style_index_0_scoped_bc4e1f96_lang = '';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,normalizeClass:_normalizeClass,resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createVNode:_createVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "bar" };
const _hoisted_2 = { class: "bar__id" };
const _hoisted_3 = { class: "bar__names" };
const _hoisted_4 = { class: "bar__view p115-endpoint-tag" };
const _hoisted_5 = { class: "bar__tools" };


const _sfc_main = {
  __name: 'AppBar',
  props: {
  view: { type: String, default: '' },
  online: { type: Boolean, default: false },
  showSwitch: { type: Boolean, default: true },
  busy: { type: Boolean, default: false },
  showRefresh: { type: Boolean, default: false },
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
    _createElementVNode("div", _hoisted_2, [
      _cache[4] || (_cache[4] = _createElementVNode("span", {
        class: "bar__glyph",
        "aria-hidden": "true"
      }, "115", -1)),
      _createElementVNode("span", _hoisted_3, [
        _cache[3] || (_cache[3] = _createElementVNode("span", { class: "bar__name" }, "轻量助手", -1)),
        _createElementVNode("span", _hoisted_4, _toDisplayString(__props.view), 1)
      ])
    ]),
    _createElementVNode("span", {
      class: _normalizeClass(["bar__link", { 'bar__link--on': __props.online }])
    }, [
      _cache[5] || (_cache[5] = _createElementVNode("span", {
        class: "bar__dot",
        "aria-hidden": "true"
      }, null, -1)),
      _createTextVNode(" " + _toDisplayString(__props.online ? '已连接 115' : '未连接 115'), 1)
    ], 2),
    _createElementVNode("div", _hoisted_5, [
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
            "aria-label": __props.view === '运行台' ? '前往设置' : '前往运行台',
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
const AppBar = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-bc4e1f96"]]);

const PLUGIN_ID = 'P115LiteAssistant';

// 与后端 notify.py 的 NOTIFY_TYPE_NAMES/SWITCHS_NAMES 一致（均自 MoviePilot MessageType 源派生）。
// 运行时后端 get_config 会注入 notify_types（同步优先），此静态表仅作加载期回退。
const NOTIFY_TYPES = [
  { title: '资源下载', value: 'Download' },
  { title: '整理入库', value: 'Organize' },
  { title: '订阅', value: 'Subscribe' },
  { title: '站点', value: 'SiteMessage' },
  { title: '媒体服务器', value: 'MediaServer' },
  { title: '手动处理', value: 'Manual' },
  { title: '插件', value: 'Plugin' },
  { title: '智能体', value: 'Agent' },
  { title: '其它', value: 'Other' },
];

const DEFAULT_CONFIG = {
  enabled: false,
  cookie: '',
  moviepilot_address: '',
  link_redirect_mode: 'cookie',
  strm_incremental: true,
  strm_download_sidecars: false,
  strm_delete_cloud_on_missing: false,
  strm_notify: false,
  strm_notify_type: 'Organize',
  strm_mappings: [],
  upload_mappings: [],
  upload_notify: false,
  upload_notify_type: 'Organize',
  upload_include_sidecars: true,
  upload_generate_strm: false,
  upload_delete_source: false,
  upload_media_extensions: '.mp4,.mkv,.ts,.iso,.rmvb,.avi,.mov,.mpeg,.mpg,.wmv,.3gp,.asf,.m4v,.flv,.m2ts,.tp,.f4v',
  upload_sidecar_extensions: '.nfo,.jpg,.jpeg,.png,.webp,.srt,.ass,.ssa,.sup',
  checkin_enabled: false,
  checkin_cron: '15 8 * * *',
  checkin_time_range: '06:00-09:00',
  checkin_notify: false,
  checkin_notify_type: 'Plugin',
  same_playback: false,
  life_monitor_enabled: false,
};

function clone(value) {
  return JSON.parse(JSON.stringify(value || {}))
}

function newId() {
  return globalThis.crypto?.randomUUID?.() || `m${Date.now()}${Math.random().toString(16).slice(2, 8)}`
}

function normalizeConfig(value = {}) {
  const config = { ...clone(DEFAULT_CONFIG), ...clone(value) };
  config.strm_mappings = Array.isArray(config.strm_mappings)
    ? config.strm_mappings.map(mapping => ({ id: newId(), ...mapping }))
    : [];
  config.upload_mappings = Array.isArray(config.upload_mappings)
    ? config.upload_mappings.map(mapping => ({ id: newId(), strm_target: '', ...mapping }))
    : [];
  return config
}

function unwrap(response) {
  if (response && typeof response === 'object' && response.data && !Object.prototype.hasOwnProperty.call(response, 'success')) {
    return response.data
  }
  return response || {}
}

async function pluginGet(api, path, params) {
  if (!api?.get) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  const response = unwrap(await api.get(`plugin/${PLUGIN_ID}${path}`, { params }));
  return Object.prototype.hasOwnProperty.call(response, 'data') ? response.data : response
}

async function pluginPost(api, path, payload = {}) {
  if (!api?.post) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  const response = unwrap(await api.post(`plugin/${PLUGIN_ID}${path}`, payload));
  return {
    success: response.success !== false,
    message: response.message || '',
    data: Object.prototype.hasOwnProperty.call(response, 'data') ? response.data : response,
  }
}

/**
 * MoviePilot 通过 provide('moviepilot:toast') 把宿主的消息条交给远程组件，
 * 这样插件不会再挂载自己的一套通知容器。宿主缺席时（独立联调）退回本地条。
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

export { AppBar as A, NOTIFY_TYPES as N, _export_sfc as _, pluginPost as a, newId as b, clone as c, normalizeConfig as n, pluginGet as p, useHostNotice as u };
