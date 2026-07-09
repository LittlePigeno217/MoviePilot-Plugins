const PLUGIN_ID = 'U115MediaUpload';

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

function normalizeResponse(result, fallback = {}) {
  if (result?.success && result?.data !== undefined) {
    return result.data
  }
  return result?.data || result || fallback
}

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

export { _export_sfc as _, normalizeResponse as n, pluginRequest as p };
