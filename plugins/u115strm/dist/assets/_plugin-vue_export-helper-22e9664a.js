// 与插件后端 API 交互的统一助手。
// MoviePilot 将 axios 实例作为 `api` prop 注入各联邦组件。
const PLUGIN_ID = 'U115Strm';

async function pluginRequest(api, path, options = {}) {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  const apiPath = `plugin/${PLUGIN_ID}${normalized}`;
  const method = (options.method || 'GET').toUpperCase();
  if (method === 'GET') {
    return await api.get(apiPath, { params: options.params })
  }
  if (method === 'POST') {
    return await api.post(apiPath, options.body ?? options.data ?? {})
  }
  return await api.request({ url: apiPath, method, data: options.body, params: options.params })
}

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

export { _export_sfc as _, pluginRequest as p };
