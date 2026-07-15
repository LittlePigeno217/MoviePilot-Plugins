const PLUGIN_ID = 'P115LiteAssistant';

const DEFAULT_CONFIG = {
  enabled: false,
  cookie: '',
  app_id: '',
  strm_incremental: true,
  strm_mappings: [],
  upload_mappings: [],
  upload_include_sidecars: true,
  upload_delete_source: false,
  upload_media_extensions: '.mkv,.mp4,.ts,.m2ts,.avi,.mov,.wmv,.iso,.rmvb,.flv',
  upload_sidecar_extensions: '.nfo,.jpg,.jpeg,.png,.webp,.srt,.ass,.ssa,.sup',
  checkin_enabled: false,
  checkin_cron: '15 8 * * *',
  checkin_time_range: '06:00-09:00',
};

function clone(value) {
  return JSON.parse(JSON.stringify(value || {}))
}

function normalizeConfig(value = {}) {
  return { ...clone(DEFAULT_CONFIG), ...clone(value) }
}

function unwrap(response) {
  if (response && typeof response === 'object' && response.data && !Object.prototype.hasOwnProperty.call(response, 'success')) {
    return response.data
  }
  return response || {}
}

async function pluginGet(api, path, params) {
  const response = unwrap(await api.get(`plugin/${PLUGIN_ID}${path}`, { params }));
  return Object.prototype.hasOwnProperty.call(response, 'data') ? response.data : response
}

async function pluginPost(api, path, payload = {}) {
  const response = unwrap(await api.post(`plugin/${PLUGIN_ID}${path}`, payload));
  return {
    success: response.success !== false,
    message: response.message || '',
    data: Object.prototype.hasOwnProperty.call(response, 'data') ? response.data : response,
  }
}

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

export { _export_sfc as _, pluginPost as a, clone as c, normalizeConfig as n, pluginGet as p };
