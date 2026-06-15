const PLUGIN_ID = 'Checkin';

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

function normalizeConfig(value = {}) {
  const config = {
    ...clone(DEFAULT_CONFIG),
    ...clone(value),
  };

  config.sites = {
    flzt: {
      ...DEFAULT_CONFIG.sites.flzt,
      ...(value.sites?.flzt || {}),
    },
    right_forum: {
      ...DEFAULT_CONFIG.sites.right_forum,
      ...(value.sites?.right_forum || {}),
    },
    ypojie: {
      ...DEFAULT_CONFIG.sites.ypojie,
      ...(value.sites?.ypojie || {}),
    },
  };

  return config
}

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
  if (!body || typeof body !== 'object') {
    return { success: true, message: '', data: body }
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
    }
  }

  return { success: true, message: '', data: body }
}

async function pluginGet(api, path) {
  return unwrapData(await api.get(`plugin/${PLUGIN_ID}${path}`))
}

async function pluginPost(api, path, payload = {}) {
  return unwrapResult(await api.post(`plugin/${PLUGIN_ID}${path}`, payload))
}

function statusColor(status = '') {
  if (['全部成功', '签到成功', '今日已签到'].includes(status)) return 'success'
  if (status === '部分成功') return 'warning'
  if (status === '执行失败') return 'error'
  return 'info'
}

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
    if (!site?.enabled) continue
    const cookie = String(site.cookie || '').trim();
    if (!cookie) errors.push(`${SITE_META[key].title} 已启用但 Cookie 未填写`);
    else if (!cookie.includes('=') || cookie.length < 20) errors.push(`${SITE_META[key].title} Cookie 格式异常`);
  }

  return errors
}

export { SITE_META as S, pluginPost as a, clone as c, normalizeConfig as n, pluginGet as p, statusColor as s, validateConfig as v };
