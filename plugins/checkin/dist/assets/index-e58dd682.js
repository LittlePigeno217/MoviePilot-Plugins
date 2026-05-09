const flztSiteMeta = {
  key: 'flzt',
  title: 'FLZT',
  subtitle: '流程：账号密码登录 `FLZT` → 调用签到接口 → 保存站点结果。',
  mode: '账号密码',
  icon: 'mdi-web-check',
  color: 'success',
};

function normalizeFlztConfig(config = {}) {
  return {
    enabled: Boolean(config.enabled),
    use_proxy: Boolean(config.use_proxy),
    email: config.email || '',
    password: config.password || '',
  }
}

const rightForumSiteMeta = {
  key: 'right_forum',
  title: '恩山无线论坛',
  subtitle: '当前采用 Cookie 方式签到，不走自动账号密码登录。',
  mode: 'Cookie',
  icon: 'mdi-forum-outline',
  color: 'warning',
};

function normalizeRightForumConfig(config = {}) {
  return {
    enabled: Boolean(config.enabled),
    use_proxy: Boolean(config.use_proxy),
    cookie: config.cookie || '',
  }
}

function validateRightForumCookie(cookie = '') {
  const value = String(cookie || '').trim();
  if (!value) {
    return '启用恩山无线论坛前，请先填写 Cookie'
  }
  if (value.length < 20) {
    return '论坛 Cookie 长度过短，请粘贴完整浏览器 Cookie'
  }
  if (!value.includes('=') || !value.includes(';')) {
    return '论坛 Cookie 格式异常，应类似 key=value; key2=value2'
  }
  const lower = value.toLowerCase();
  if (!lower.includes('auth') && !lower.includes('saltkey') && !lower.includes('sid')) {
    return '论坛 Cookie 缺少常见登录字段，可能不是登录后的完整 Cookie'
  }
  return ''
}

const ypojieSiteMeta = {
  key: 'ypojie',
  title: '易破解',
  subtitle: '当前采用 Cookie 方式签到，通过 WordPress AJAX 接口完成每日签到。',
  mode: 'Cookie',
  icon: 'mdi-account-check-outline',
  color: 'primary',
};

function normalizeYpojieConfig(config = {}) {
  return {
    enabled: Boolean(config.enabled),
    use_proxy: Boolean(config.use_proxy),
    cookie: config.cookie || '',
  }
}

function validateYpojieCookie(cookie = '') {
  const value = String(cookie || '').trim();
  if (!value) {
    return '启用易破解前，请先填写 Cookie'
  }
  if (value.length < 20) {
    return '易破解 Cookie 长度过短，请粘贴完整浏览器 Cookie'
  }
  if (!value.includes('=') || !value.includes(';')) {
    return '易破解 Cookie 格式异常，应类似 key=value; key2=value2'
  }
  return ''
}

const siteMetaMap = {
  [flztSiteMeta.key]: flztSiteMeta,
  [rightForumSiteMeta.key]: rightForumSiteMeta,
  [ypojieSiteMeta.key]: ypojieSiteMeta,
};

function getSiteMeta(siteKey) {
  return siteMetaMap[siteKey] || {
    key: siteKey,
    title: siteKey,
    subtitle: '',
    mode: '未知',
    icon: 'mdi-web',
    color: 'primary',
  }
}

const PLUGIN_ID = 'Checkin';

function pluginPath(path = '') {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `/api/v1/plugin/${PLUGIN_ID}${normalized}`
}

async function pluginRequest(api, path, options = {}) {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  const apiPath = `plugin/${PLUGIN_ID}${normalized}`;
  const method = (options.method || 'GET').toUpperCase();
  const payload = options.body ?? options.payload ?? undefined;

  if (method === 'POST' && api?.post) {
    return api.post(apiPath, payload || {}, options)
  }
  if (method === 'GET' && api?.get) {
    return api.get(apiPath, options)
  }

  const response = await fetch(pluginPath(normalized), {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    body: method === 'POST' ? JSON.stringify(payload || {}) : undefined,
  });
  return response.json()
}

function cloneConfig(config = {}) {
  return JSON.parse(JSON.stringify(config || {}))
}

function normalizeSiteConfig(sites = {}) {
  return {
    flzt: normalizeFlztConfig(sites.flzt || {}),
    right_forum: normalizeRightForumConfig(sites.right_forum || {}),
    ypojie: normalizeYpojieConfig(sites.ypojie || {}),
  }
}

function getSiteDisplayMeta(siteKey) {
  return getSiteMeta(siteKey)
}

function statusColor(status) {
  if (status === '签到成功') return 'success'
  if (status === '今日已签到') return 'warning'
  if (status === '执行失败') return 'error'
  return 'info'
}

export { validateYpojieCookie as a, cloneConfig as c, flztSiteMeta as f, getSiteDisplayMeta as g, normalizeSiteConfig as n, pluginRequest as p, rightForumSiteMeta as r, statusColor as s, validateRightForumCookie as v, ypojieSiteMeta as y };
