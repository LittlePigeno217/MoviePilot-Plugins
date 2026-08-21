// 自用签到工具 —— 前端共享模块
// 站点元数据、配置规范化与校验、请求封装。与后端 API 契约保持一致。

export const PLUGIN_ID = 'Checkin'

// 站点元数据：key、显示名、登录方式、卡面缩写
export const SITE_META = {
  flzt: { key: 'flzt', title: 'FLZT', mode: '账号密码', badge: 'FZ' },
  right_forum: { key: 'right_forum', title: '恩山无线论坛', mode: 'Cookie', badge: 'ES' },
  ypojie: { key: 'ypojie', title: '易破解', mode: '账号密码', badge: 'YP' },
}

export const SITE_KEYS = Object.keys(SITE_META)

export const DEFAULT_CONFIG = {
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
}

export function clone(value) {
  return JSON.parse(JSON.stringify(value || {}))
}

// 把后端返回补齐为完整结构，缺字段不会让 v-model 绑定炸掉
export function normalizeConfig(value = {}) {
  const config = { ...clone(DEFAULT_CONFIG), ...clone(value) }
  config.sites = {}
  for (const key of SITE_KEYS) {
    config.sites[key] = { ...DEFAULT_CONFIG.sites[key], ...(value.sites?.[key] || {}) }
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
  const body = unwrapTransport(response)
  if (body && typeof body === 'object' && Object.prototype.hasOwnProperty.call(body, 'data')) {
    return body.data ?? {}
  }
  return body ?? {}
}

function unwrapResult(response) {
  const body = unwrapTransport(response)
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

export async function pluginGet(api, path) {
  if (!api?.get) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  return unwrapData(await api.get(`plugin/${PLUGIN_ID}${path}`))
}

export async function pluginPost(api, path, payload = {}) {
  if (!api?.post) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  return unwrapResult(await api.post(`plugin/${PLUGIN_ID}${path}`, payload))
}

// 保存前校验，和后端 validate_config 的规则对齐
export function validateConfig(config) {
  const errors = []
  const sites = config.sites || {}

  for (const key of ['flzt', 'ypojie']) {
    const site = sites[key]
    if (site?.enabled && (!site.email || !site.password)) {
      errors.push(`${SITE_META[key].title} 已启用但账号或密码未填写`)
    }
  }

  const forum = sites.right_forum
  if (forum?.enabled) {
    const cookie = String(forum.cookie || '').trim()
    if (!cookie) errors.push(`${SITE_META.right_forum.title} 已启用但 Cookie 未填写`)
    else if (!cookie.includes('=') || cookie.length < 20) errors.push(`${SITE_META.right_forum.title} Cookie 格式异常`)
  }

  return errors
}

/**
 * MoviePilot 通过 provide('moviepilot:toast') 把宿主的消息条交给远程组件。
 * 宿主缺席时（独立联调）退回本地提示条。
 */
export function useHostNotice(injected, local) {
  const speak = (text, kind = 'info') => {
    const message = String(text || '').trim()
    if (!message) return
    const host = injected?.value ?? injected
    const method = host?.[kind] || host?.info
    if (typeof method === 'function') {
      method.call(host, message)
      return
    }
    if (typeof host === 'function') {
      host(message, kind)
      return
    }
    local(message, kind)
  }
  return {
    info: text => speak(text, 'info'),
    success: text => speak(text, 'success'),
    error: text => speak(text, 'error'),
    warning: text => speak(text, 'warning'),
    say: speak,
  }
}
