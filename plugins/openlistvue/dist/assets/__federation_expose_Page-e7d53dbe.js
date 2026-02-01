import { importShared } from './__federation_fn_import-054b33c3.js';
import { a as apiService, d as debounce, t as throttle } from './api-5bacd28b.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const Page_vue_vue_type_style_index_0_scoped_8d28d9fa_lang = '';

const {defineComponent,ref,onMounted,onUnmounted} = await importShared('vue');

const _sfc_main = defineComponent({
  name: 'Page',
  props: {
    api: {
      type: Object,
      default: () => {}
    }
  },
  emits: ['action', 'switch', 'close'],
  setup(props, { emit }) {
    // 状态管理
    const taskStatus = ref({
      status: 'idle',
      progress: 0,
      message: '',
      last_run: null,
      total_files: 0,
      copied_files: 0,
      skipped_files: 0
    });

    const authStatus = ref({
      connected: false,
      message: '未检查',
      status: '未连接',
      timestamp: new Date().toLocaleString()
    });

    const fileIdentifierStats = ref({
      total: 0,
      completed: 0,
      copying: 0
    });

    const config = ref({});
    const loading = ref(false);
    const error = ref('');
    const pollingInterval = ref(null);

    // 初始化API服务
    if (props.api) {
      apiService.setApiInstance(props.api);
    }

    // 数据加载
    const loadCombinedData = async (forceRefresh = false) => {
      if (loading.value) return
      
      loading.value = true;
      error.value = '';
      
      try {
        const response = await apiService.get('/plugin/OpenListVue/combined', {}, {
          cache: !forceRefresh,
          cacheDuration: 30000 // 30秒缓存
        });
        
        if (response.data) {
          updateStateFromData(response.data);
        }
      } catch (err) {
        error.value = `加载数据失败: ${err.message}`;
        console.error('加载合并数据失败:', err);
        await loadFallbackData(forceRefresh);
      } finally {
        loading.value = false;
      }
    };

    const updateStateFromData = (data) => {
      if (data.status) {
        taskStatus.value = {
          status: data.status.task_status?.status || 'idle',
          progress: data.status.task_status?.progress || 0,
          message: data.status.task_status?.message || '',
          last_run: data.status.task_status?.last_run || null,
          total_files: data.status.task_status?.total_files || 0,
          copied_files: data.status.task_status?.copied_files || 0,
          skipped_files: data.status.task_status?.skipped_files || 0
        };
      }
      
      if (data.auth) {
        authStatus.value = {
          connected: data.auth.connected || false,
          message: data.auth.message || '未检查',
          status: data.auth.status || '未连接',
          timestamp: data.auth.timestamp || new Date().toLocaleString()
        };
      }
      
      if (data.config) {
        config.value = data.config;
      }
      
      if (data.status?.file_identifier_stats) {
        console.log('Received file_identifier_stats:', data.status.file_identifier_stats);
        fileIdentifierStats.value = data.status.file_identifier_stats;
      } else {
        console.log('No file_identifier_stats received:', data.status);
      }
    };

    const loadFallbackData = async (forceRefresh = false) => {
      try {
        // 加载任务状态
        const statusResponse = await apiService.get('/plugin/OpenListVue/status', {}, {
          cache: !forceRefresh,
          cacheDuration: 60000 // 1分钟缓存
        });
        
        if (statusResponse.data) {
          taskStatus.value = statusResponse.data;
          // 处理文件标识统计信息
          if (statusResponse.data.file_identifier_stats) {
            fileIdentifierStats.value = statusResponse.data.file_identifier_stats;
          }
        }
        
        // 加载认证状态
        await loadAuthStatus();
      } catch (err) {
        console.error('加载备用数据失败:', err);
      }
    };

    const loadAuthStatus = async () => {
      try {
        // 获取配置
        const configResponse = await apiService.get('/plugin/OpenListVue/config', {}, {
          cache: true,
          cacheDuration: 60000 // 1分钟缓存
        });
        
        if (configResponse.data) {
          const { openlist_url, openlist_token } = configResponse.data;
          
          if (openlist_url && openlist_token) {
            // 验证OpenList连接
            const authResponse = await fetch(`${openlist_url}/api/me`, {
              headers: {
                'Authorization': openlist_token,
                'Content-Type': 'application/json'
              }
            });
            
            if (authResponse.ok) {
              const data = await authResponse.json();
              const isConnected = data.code === 200;
              authStatus.value = {
                connected: isConnected,
                message: isConnected ? '连接成功' : '连接失败',
                status: isConnected ? '通过' : '未连接',
                timestamp: new Date().toLocaleString()
              };
            } else {
              throw new Error(`认证请求失败: ${authResponse.status}`)
            }
          } else {
            authStatus.value = {
              connected: false,
              message: 'OpenList地址或令牌未配置',
              status: '未连接',
              timestamp: new Date().toLocaleString()
            };
          }
        }
      } catch (err) {
        console.error('加载认证状态失败:', err);
        authStatus.value = {
          connected: false,
          message: `检查失败: ${err.message}`,
          status: '未连接',
          timestamp: new Date().toLocaleString()
        };
      }
    };

    // 任务操作
    const runCopyTask = debounce(async () => {
      if (loading.value) return
      
      loading.value = true;
      error.value = '';
      
      try {
        await apiService.post('/plugin/OpenListVue/run');
        emit('action');
        // 清除缓存，强制刷新数据
        apiService.clearCache();
        await loadCombinedData(true);
      } catch (err) {
        error.value = `执行任务失败: ${err.message}`;
        await loadAuthStatus();
      } finally {
        loading.value = false;
      }
    }, 1000);

    const refreshData = debounce(async () => {
      emit('action');
      // 清除缓存，强制刷新数据
      apiService.clearCache();
      await loadCombinedData(true);
    }, 500);

    const throttledLoadData = throttle(loadCombinedData, 2000);

    // 事件处理
    const handleSwitch = () => {
      emit('switch');
    };

    const handleClose = () => {
      emit('close');
    };

    // 生命周期
    onMounted(async () => {
      await loadCombinedData();
      // 设置轮询 - 改为5秒一次，获得更实时的任务状态更新
      pollingInterval.value = window.setInterval(() => {
        throttledLoadData();
      }, 5000);
    });

    onUnmounted(() => {
      if (pollingInterval.value) {
        clearInterval(pollingInterval.value);
      }
    });

    return {
      taskStatus,
      authStatus,
      fileIdentifierStats,
      config,
      loading,
      error,
      runCopyTask,
      refreshData,
      handleSwitch,
      handleClose
    }
  }
});

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,normalizeClass:_normalizeClass,normalizeStyle:_normalizeStyle} = await importShared('vue');


const _hoisted_1 = { class: "page-container" };
const _hoisted_2 = { class: "page-header" };
const _hoisted_3 = { class: "header-actions" };
const _hoisted_4 = ["disabled"];
const _hoisted_5 = ["disabled"];
const _hoisted_6 = {
  key: 0,
  class: "error-message"
};
const _hoisted_7 = { class: "task-status-section" };
const _hoisted_8 = { class: "execution-progress" };
const _hoisted_9 = { class: "status-info" };
const _hoisted_10 = {
  key: 0,
  class: "progress-percentage"
};
const _hoisted_11 = {
  key: 0,
  class: "progress-container"
};
const _hoisted_12 = { class: "progress-bar" };
const _hoisted_13 = {
  key: 1,
  class: "current-operation"
};
const _hoisted_14 = { class: "operation-value" };
const _hoisted_15 = {
  key: 2,
  class: "file-progress"
};
const _hoisted_16 = { class: "progress-value" };
const _hoisted_17 = {
  key: 3,
  class: "current-pair"
};
const _hoisted_18 = { class: "pair-value" };
const _hoisted_19 = { class: "file-identifier-stats" };
const _hoisted_20 = { class: "stats-grid" };
const _hoisted_21 = { class: "stat-item" };
const _hoisted_22 = { class: "stat-value" };
const _hoisted_23 = { class: "stat-item" };
const _hoisted_24 = { class: "stat-value" };
const _hoisted_25 = { class: "stat-item" };
const _hoisted_26 = { class: "stat-value" };

function _sfc_render(_ctx, _cache, $props, $setup, $data, $options) {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("header", _hoisted_2, [
      _cache[4] || (_cache[4] = _createElementVNode("h2", null, "OpenList管理Vue", -1)),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("button", {
          onClick: _cache[0] || (_cache[0] = (...args) => (_ctx.runCopyTask && _ctx.runCopyTask(...args))),
          class: "btn btn-primary",
          disabled: _ctx.loading
        }, _toDisplayString(_ctx.loading ? '执行中...' : '执行复制任务'), 9, _hoisted_4),
        _createElementVNode("button", {
          onClick: _cache[1] || (_cache[1] = (...args) => (_ctx.refreshData && _ctx.refreshData(...args))),
          class: "btn btn-secondary",
          disabled: _ctx.loading
        }, " 刷新数据 ", 8, _hoisted_5),
        _createElementVNode("button", {
          onClick: _cache[2] || (_cache[2] = (...args) => (_ctx.handleSwitch && _ctx.handleSwitch(...args))),
          class: "btn btn-secondary"
        }, " 配置插件 "),
        _createElementVNode("button", {
          onClick: _cache[3] || (_cache[3] = (...args) => (_ctx.handleClose && _ctx.handleClose(...args))),
          class: "btn btn-secondary"
        }, " 关闭页面 ")
      ])
    ]),
    (_ctx.error)
      ? (_openBlock(), _createElementBlock("div", _hoisted_6, _toDisplayString(_ctx.error), 1))
      : _createCommentVNode("", true),
    _createElementVNode("section", _hoisted_7, [
      _cache[12] || (_cache[12] = _createElementVNode("h3", { class: "section-title" }, "任务状态", -1)),
      _createElementVNode("div", _hoisted_8, [
        _createElementVNode("div", _hoisted_9, [
          _createElementVNode("span", {
            class: _normalizeClass(["status-badge", {
            'status-idle': _ctx.taskStatus.status === 'idle',
            'status-running': _ctx.taskStatus.status === 'running',
            'status-success': _ctx.taskStatus.status === 'success',
            'status-failed': _ctx.taskStatus.status === 'failed'
          }])
          }, _toDisplayString(_ctx.taskStatus.status === 'idle' ? '空闲' : 
               _ctx.taskStatus.status === 'running' ? '运行中' : 
               _ctx.taskStatus.status === 'success' ? '完成' : 
               _ctx.taskStatus.status === 'failed' ? '失败' : 
               _ctx.taskStatus.status), 3),
          (_ctx.taskStatus.status === 'running')
            ? (_openBlock(), _createElementBlock("span", _hoisted_10, _toDisplayString(_ctx.taskStatus.progress) + "% ", 1))
            : _createCommentVNode("", true)
        ]),
        (_ctx.taskStatus.progress > 0 || _ctx.taskStatus.status === 'running')
          ? (_openBlock(), _createElementBlock("div", _hoisted_11, [
              _createElementVNode("div", _hoisted_12, [
                _createElementVNode("div", {
                  class: "progress-fill",
                  style: _normalizeStyle({ width: `${_ctx.taskStatus.progress}%` })
                }, null, 4)
              ])
            ]))
          : _createCommentVNode("", true),
        (_ctx.taskStatus.message)
          ? (_openBlock(), _createElementBlock("div", _hoisted_13, [
              _cache[5] || (_cache[5] = _createElementVNode("span", { class: "operation-label" }, "当前操作:", -1)),
              _createElementVNode("span", _hoisted_14, _toDisplayString(_ctx.taskStatus.message), 1)
            ]))
          : _createCommentVNode("", true),
        (_ctx.taskStatus.total_files > 0)
          ? (_openBlock(), _createElementBlock("div", _hoisted_15, [
              _cache[6] || (_cache[6] = _createElementVNode("span", { class: "progress-label" }, "复制进度:", -1)),
              _createElementVNode("span", _hoisted_16, _toDisplayString(_ctx.taskStatus.copied_files) + " / " + _toDisplayString(_ctx.taskStatus.total_files) + " 文件", 1)
            ]))
          : _createCommentVNode("", true),
        (_ctx.taskStatus.current_pair)
          ? (_openBlock(), _createElementBlock("div", _hoisted_17, [
              _cache[7] || (_cache[7] = _createElementVNode("span", { class: "pair-label" }, "当前处理:", -1)),
              _createElementVNode("span", _hoisted_18, _toDisplayString(_ctx.taskStatus.current_pair), 1)
            ]))
          : _createCommentVNode("", true),
        _createElementVNode("div", _hoisted_19, [
          _cache[11] || (_cache[11] = _createElementVNode("h4", { class: "stats-title" }, "文件标识统计", -1)),
          _createElementVNode("div", _hoisted_20, [
            _createElementVNode("div", _hoisted_21, [
              _cache[8] || (_cache[8] = _createElementVNode("span", { class: "stat-label" }, "总文件标识:", -1)),
              _createElementVNode("span", _hoisted_22, _toDisplayString(_ctx.fileIdentifierStats.total), 1)
            ]),
            _createElementVNode("div", _hoisted_23, [
              _cache[9] || (_cache[9] = _createElementVNode("span", { class: "stat-label" }, "已完成:", -1)),
              _createElementVNode("span", _hoisted_24, _toDisplayString(_ctx.fileIdentifierStats.completed), 1)
            ]),
            _createElementVNode("div", _hoisted_25, [
              _cache[10] || (_cache[10] = _createElementVNode("span", { class: "stat-label" }, "复制中:", -1)),
              _createElementVNode("span", _hoisted_26, _toDisplayString(_ctx.fileIdentifierStats.copying), 1)
            ])
          ])
        ])
      ])
    ])
  ]))
}
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['render',_sfc_render],['__scopeId',"data-v-8d28d9fa"]]);

export { Page as default };
