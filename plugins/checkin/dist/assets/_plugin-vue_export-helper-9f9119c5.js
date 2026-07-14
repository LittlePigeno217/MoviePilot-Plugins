// 签到插件前端共享模块：站点元数据、配置规范化、请求封装、状态色。
// 逻辑与后端 API 契约保持一致，仅供 Page.vue / Config.vue 复用。

const PLUGIN_ID = 'Checkin';

// 站点元数据（key、显示名、登录方式、印色）
const SITE_META = {
  flzt: {
    key: 'flzt',
    title: 'FLZT',
    mode: '账号密码',
    icon: 'mdi-web-check',
    color: 'success',
  },
  right_forum: {
    key: 'right_forum',
    title: '恩山无线论坛',
    mode: 'Cookie',
    icon: 'mdi-forum-outline',
    color: 'warning',
  },
  ypojie: {
    key: 'ypojie',
    title: '易破解',
    mode: '账号密码',
    icon: 'mdi-account-check-outline',
    color: 'primary',
  },
};

// 默认配置
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
  return JSON.parse(JSON.stringify(value || {}));
}

// 将后端返回/历史配置补齐为完整结构，避免缺字段导致的绑定报错
function normalizeConfig(value = {}) {
  const config = {
    ...clone(DEFAULT_CONFIG),
    ...clone(value),
  };

  config.sites = {
    flzt: { ...DEFAULT_CONFIG.sites.flzt, ...(value.sites?.flzt || {}) },
    right_forum: { ...DEFAULT_CONFIG.sites.right_forum, ...(value.sites?.right_forum || {}) },
    ypojie: { ...DEFAULT_CONFIG.sites.ypojie, ...(value.sites?.ypojie || {}) },
  };

  return config;
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
    return response.data;
  }
  return response;
}

function unwrapData(response) {
  const body = unwrapTransport(response);
  if (body && typeof body === 'object' && Object.prototype.hasOwnProperty.call(body, 'data')) {
    return body.data ?? {};
  }
  return body ?? {};
}

function unwrapResult(response) {
  const body = unwrapTransport(response);
  if (!body || typeof body !== 'object') {
    return { success: true, message: '', data: body };
  }

  if (
    Object.prototype.hasOwnProperty.call(body, 'success')
    || Object.prototype.hasOwnProperty.call(body, 'message')
    || Object.prototype.hasOwnProperty.call(body, 'data')
  ) {
    return {
      success: body.success !== false,
      message: body.message || '',
      data: body.data,
    };
  }

  return { success: true, message: '', data: body };
}

async function pluginGet(api, path) {
  return unwrapData(await api.get(`plugin/${PLUGIN_ID}${path}`));
}

async function pluginPost(api, path, payload = {}) {
  return unwrapResult(await api.post(`plugin/${PLUGIN_ID}${path}`, payload));
}

// 保存前的配置校验
function validateConfig(config) {
  const errors = [];
  const sites = config.sites || {};

  for (const key of ['flzt', 'ypojie']) {
    const site = sites[key];
    if (site?.enabled && (!site.email || !site.password)) {
      errors.push(`${SITE_META[key].title} 已启用但账号或密码未填写`);
    }
  }

  for (const key of ['right_forum']) {
    const site = sites[key];
    if (!site?.enabled) continue;
    const cookie = String(site.cookie || '').trim();
    if (!cookie) errors.push(`${SITE_META[key].title} 已启用但 Cookie 未填写`);
    else if (!cookie.includes('=') || cookie.length < 20) errors.push(`${SITE_META[key].title} Cookie 格式异常`);
  }

  return errors;
}

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

export { SITE_META as S, _export_sfc as _, pluginPost as a, clone as c, normalizeConfig as n, pluginGet as p, validateConfig as v };
