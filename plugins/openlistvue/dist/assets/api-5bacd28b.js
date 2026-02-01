class ApiService {
  baseURL;
  timeout;
  headers;
  cache;
  api;
  constructor(config = {}) {
    this.baseURL = config.baseURL || "";
    this.timeout = config.timeout || 3e4;
    this.headers = config.headers || {};
    this.cache = /* @__PURE__ */ new Map();
    this.api = null;
  }
  // 设置API实例
  setApiInstance(api) {
    this.api = api;
  }
  // 生成缓存键
  generateCacheKey(url, params) {
    const key = `${url}${params ? JSON.stringify(params) : ""}`;
    return key;
  }
  // 缓存操作
  getCache(key) {
    const item = this.cache.get(key);
    if (item && item.timestamp + item.duration > Date.now()) {
      return item.value;
    }
    this.cache.delete(key);
    return null;
  }
  setCache(key, value, duration) {
    this.cache.set(key, {
      value,
      timestamp: Date.now(),
      duration
    });
  }
  // 请求方法
  async request(method, url, data, config) {
    const cacheConfig = config?.cache !== false;
    const cacheDuration = config?.cacheDuration || 3e4;
    const skipErrorHandling = config?.skipErrorHandling || false;
    const cacheKey = this.generateCacheKey(url, method === "get" ? data : void 0);
    if (cacheConfig && method === "get") {
      const cachedData = this.getCache(cacheKey);
      if (cachedData) {
        console.log(`[Cache Hit] ${url}`);
        return { data: cachedData, success: true };
      }
    }
    try {
      let response;
      if (this.api) {
        if (method === "get") {
          response = await this.api.get(url, data);
        } else if (method === "post") {
          response = await this.api.post(url, data);
        } else {
          throw new Error(`Unsupported method: ${method}`);
        }
      } else {
        const fetchConfig = {
          method: method.toUpperCase(),
          headers: {
            "Content-Type": "application/json",
            ...this.headers
          }
        };
        if (method !== "get" && data) {
          fetchConfig.body = JSON.stringify(data);
        }
        const fetchResponse = await fetch(`${this.baseURL}${url}`, fetchConfig);
        response = { data: await fetchResponse.json() };
      }
      if (cacheConfig && method === "get" && response.data) {
        this.setCache(cacheKey, response.data, cacheDuration);
      }
      return {
        data: response.data,
        success: true
      };
    } catch (error) {
      console.error(`[API Error] ${url}:`, error);
      if (skipErrorHandling) {
        throw error;
      }
      return {
        error: true,
        message: error.message || "请求失败"
      };
    }
  }
  // GET请求
  async get(url, params, config) {
    return this.request("get", url, params, config);
  }
  // POST请求
  async post(url, data, config) {
    return this.request("post", url, data, config);
  }
  // 清除客户端缓存
  clearCache(key) {
    if (key) {
      this.cache.delete(key);
    } else {
      this.cache.clear();
    }
  }
  // 调用后端 API 清除插件缓存
  async clearPluginCache() {
    try {
      this.clearCache();
      const response = await this.post("/plugin/OpenListVue/clear_cache");
      return response;
    } catch (error) {
      console.error("清除缓存失败:", error);
      return {
        error: true,
        message: error.message || "清除缓存失败"
      };
    }
  }
  // 获取配置
  async getConfig() {
    try {
      const response = await this.get("/plugin/OpenListVue/config");
      return response.data;
    } catch (error) {
      console.error("获取配置失败:", error);
      return null;
    }
  }
  // 获取缓存大小
  getCacheSize() {
    return this.cache.size;
  }
}
const apiService = new ApiService();
const debounce = (func, wait) => {
  let timeout = null;
  return (...args) => {
    if (timeout)
      clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
};
const throttle = (func, limit) => {
  let inThrottle = false;
  return (...args) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
};

export { apiService as a, debounce as d, throttle as t };
