export const PLUGIN_ID = 'P115LiteAssistant'

// 与后端 notify.py 的 NOTIFY_TYPE_NAMES 一一对应，顺序即界面顺序
export const NOTIFY_TYPES = [
  { title: '插件', value: 'Plugin' },
  { title: '整理入库', value: 'Organize' },
  { title: '站点', value: 'SiteMessage' },
  { title: '媒体服务器', value: 'MediaServer' },
  { title: '手动处理', value: 'Manual' },
  { title: '其它', value: 'Other' },
]

export const DEFAULT_CONFIG = {
  enabled: false,
  cookie: '',
  moviepilot_address: '',
  link_redirect_mode: 'cookie',
  strm_incremental: true,
  strm_download_sidecars: false,
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
}

export function clone(value) {
  return JSON.parse(JSON.stringify(value || {}))
}

export function newId() {
  return globalThis.crypto?.randomUUID?.() || `m${Date.now()}${Math.random().toString(16).slice(2, 8)}`
}

export function normalizeConfig(value = {}) {
  const config = { ...clone(DEFAULT_CONFIG), ...clone(value) }
  config.strm_mappings = Array.isArray(config.strm_mappings)
    ? config.strm_mappings.map(mapping => ({ id: newId(), ...mapping }))
    : []
  config.upload_mappings = Array.isArray(config.upload_mappings)
    ? config.upload_mappings.map(mapping => ({ id: newId(), strm_target: '', ...mapping }))
    : []
  return config
}

function unwrap(response) {
  if (response && typeof response === 'object' && response.data && !Object.prototype.hasOwnProperty.call(response, 'success')) {
    return response.data
  }
  return response || {}
}

export async function pluginGet(api, path, params) {
  if (!api?.get) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  const response = unwrap(await api.get(`plugin/${PLUGIN_ID}${path}`, { params }))
  return Object.prototype.hasOwnProperty.call(response, 'data') ? response.data : response
}

export async function pluginPost(api, path, payload = {}) {
  if (!api?.post) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  const response = unwrap(await api.post(`plugin/${PLUGIN_ID}${path}`, payload))
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
