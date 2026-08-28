import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, u as useHostNotice, A as AppBar, p as pluginGet, a as pluginPost } from './kit-a6d4b6ea.js';

const Page_vue_vue_type_style_index_0_scoped_b1b51fda_lang = '';

const {createVNode:_createVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,resolveComponent:_resolveComponent,withCtx:_withCtx} = await importShared('vue');


const _hoisted_1 = { class: "p115 run" };
const _hoisted_2 = { class: "run__body" };
const _hoisted_3 = { class: "run__strip" };
const _hoisted_4 = { class: "svc__label p115-endpoint-tag" };
const _hoisted_5 = { class: "svc__value" };
const _hoisted_6 = {
  key: 0,
  class: "svc__hint"
};
const _hoisted_7 = { class: "p115-panel" };
const _hoisted_8 = { class: "p115-panel__head" };
const _hoisted_9 = { class: "p115-hint" };
const _hoisted_10 = { class: "p115-panel__body" };
const _hoisted_11 = { class: "run__acts" };
const _hoisted_12 = { class: "p115-panel" };
const _hoisted_13 = { class: "p115-panel__head" };
const _hoisted_14 = { class: "p115-hint" };
const _hoisted_15 = { class: "p115-panel__body" };
const _hoisted_16 = {
  key: 0,
  class: "card-grid"
};
const _hoisted_17 = ["title"];
const _hoisted_18 = { class: "card__meta" };
const _hoisted_19 = { class: "card__when p115-mono" };
const _hoisted_20 = {
  key: 1,
  class: "p115-empty"
};
const _hoisted_21 = { class: "p115-panel" };
const _hoisted_22 = { class: "p115-panel__body" };
const _hoisted_23 = {
  key: 0,
  class: "log"
};
const _hoisted_24 = { class: "log__kind" };
const _hoisted_25 = { class: "log__when p115-mono" };
const _hoisted_26 = { class: "log__tally" };
const _hoisted_27 = {
  key: 0,
  class: "log__cost p115-mono"
};
const _hoisted_28 = {
  key: 1,
  class: "p115-empty"
};

const {computed,inject,onMounted,reactive,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: [Object, Function], default: null },
  show_switch: { type: Boolean, default: false },
},
  emits: ['switch', 'close', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const status = ref({ running: [], recent_uploads: [], history: [] });
const busy = ref(false);
const local = reactive({ text: '', kind: 'info' });
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text;
  local.kind = kind;
});

const uploads = computed(() => status.value.recent_uploads || []);
const visibleUploads = computed(() => uploads.value.slice(0, 10));
const history = computed(() => status.value.history || []);
const running = computed(() => status.value.running || []);
const workingNow = computed(() => running.value.some(kind => kind === 'strm' || kind === 'upload'));

const kindNames = { strm: '生成 STRM', upload: '上传', checkin: '签到' };

// 服务条：每一项都是“现在能不能干活”的答案，不是装饰性的计数
const services = computed(() => [
  {
    key: 'auth',
    label: '115 授权',
    value: status.value.authenticated ? '已连接' : '未登录',
    ok: Boolean(status.value.authenticated),
    hint: status.value.authenticated ? '' : '去设置里扫码登录',
  },
  {
    key: 'strm',
    label: 'STRM 通道',
    value: `${status.value.strm_mappings || 0} 条`,
    ok: Boolean(status.value.strm_mappings),
    hint: status.value.strm_mappings ? '' : '还没有配置通道',
  },
  {
    key: 'upload',
    label: '上传通道',
    value: `${status.value.upload_mappings || 0} 条`,
    ok: Boolean(status.value.upload_mappings),
    hint: status.value.upload_mappings ? '' : '还没有配置通道',
  },
  {
    key: 'life',
    label: '生活事件',
    value: status.value.life_monitor_running ? '监听中' : status.value.life_monitor_enabled ? '等待启动' : '未启用',
    ok: Boolean(status.value.life_monitor_running),
    hint: '',
  },
]);

const actions = [
  { key: 'strm', label: '生成 STRM', icon: 'mdi-file-link-outline', path: '/strm/sync', payload: {} },
  { key: 'full', label: '全量上传', icon: 'mdi-tray-arrow-up', path: '/upload', payload: { incremental: false } },
  { key: 'inc', label: '增量上传', icon: 'mdi-tray-plus-outline', path: '/upload', payload: { incremental: true } },
  { key: 'checkin', label: '立即签到', icon: 'mdi-calendar-check-outline', path: '/checkin', payload: {} },
];

async function refresh() {
  if (!props.api) return
  busy.value = true;
  try {
    status.value = await pluginGet(props.api, '/status');
  } catch (error) {
    notice.error(error?.message || '状态获取失败');
  } finally {
    busy.value = false;
  }
}

async function run(action) {
  try {
    const result = await pluginPost(props.api, action.path, action.payload);
    if (result.success) notice.success(result.message || `${action.label}已开始`);
    else notice.error(result.message || `${action.label}未能开始`);
    await refresh();
    emit('action');
  } catch (error) {
    notice.error(error?.message || `${action.label}失败`);
  }
}

function seconds(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value <= 0) return ''
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(1)}s`
}

// 每种任务只汇报它自己有意义的那几个数，避免整排 0
function tally(entry) {
  const pick = keys => keys.filter(([, key]) => Number(entry[key]) > 0).map(([label, key]) => `${label} ${entry[key]}`);
  if (entry.kind === 'strm') {
    const parts = pick([['新增', 'added'], ['更新', 'updated'], ['清理', 'removed'], ['附加', 'sidecars'], ['跳过', 'skipped'], ['冲突', 'conflicts'], ['失败', 'errors']]);
    return parts.length ? parts : ['没有变化']
  }
  if (entry.kind === 'upload') {
    const parts = pick([['上传', 'uploaded'], ['秒传', 'instant'], ['STRM', 'strm_generated'], ['跳过', 'skipped'], ['删除', 'deleted'], ['延后', 'deferred'], ['失败', 'errors']]);
    return parts.length ? parts : ['没有变化']
  }
  if (entry.kind === 'checkin') {
    const parts = [];
    if (entry.already) parts.push('今天已签过');
    if (Number(entry.continuous_day) > 0) parts.push(`连续 ${entry.continuous_day} 天`);
    if (Number(entry.points_num) > 0) parts.push(`+${entry.points_num} 积分`);
    return parts.length ? parts : [entry.message || '已签到']
  }
  return [entry.message || '已完成']
}

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(AppBar, {
      view: "运行台",
      online: Boolean(status.value.authenticated),
      "show-switch": __props.show_switch,
      busy: busy.value,
      "show-refresh": "",
      onRefresh: refresh,
      onSwitch: _cache[0] || (_cache[0] = $event => (emit('switch'))),
      onClose: _cache[1] || (_cache[1] = $event => (emit('close')))
    }, null, 8, ["online", "show-switch", "busy"]),
    (local.text)
      ? (_openBlock(), _createElementBlock("button", {
          key: 0,
          type: "button",
          class: _normalizeClass(["run__local", `run__local--${local.kind}`]),
          onClick: _cache[2] || (_cache[2] = $event => (local.text = ''))
        }, [
          _createTextVNode(_toDisplayString(local.text) + " ", 1),
          _cache[3] || (_cache[3] = _createElementVNode("span", { class: "run__local-dismiss" }, "知道了", -1))
        ], 2))
      : _createCommentVNode("", true),
    _createElementVNode("div", _hoisted_2, [
      _createElementVNode("div", _hoisted_3, [
        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(services.value, (item) => {
          return (_openBlock(), _createElementBlock("div", {
            key: item.key,
            class: _normalizeClass(["svc", { 'svc--ok': item.ok }])
          }, [
            _createElementVNode("span", _hoisted_4, _toDisplayString(item.label), 1),
            _createElementVNode("span", _hoisted_5, _toDisplayString(item.value), 1),
            (item.hint)
              ? (_openBlock(), _createElementBlock("span", _hoisted_6, _toDisplayString(item.hint), 1))
              : _createCommentVNode("", true)
          ], 2))
        }), 128))
      ]),
      _createElementVNode("div", _hoisted_7, [
        _createElementVNode("div", _hoisted_8, [
          _createElementVNode("div", null, [
            _cache[4] || (_cache[4] = _createElementVNode("h3", { class: "p115-section-title" }, "手动跑一次", -1)),
            _createElementVNode("p", _hoisted_9, _toDisplayString(workingNow.value ? `正在跑：${running.value.map(kind => kindNames[kind] || kind).join('、')}` : '当前空闲，按需触发。'), 1)
          ])
        ]),
        _createElementVNode("div", _hoisted_10, [
          _createElementVNode("div", _hoisted_11, [
            (_openBlock(), _createElementBlock(_Fragment, null, _renderList(actions, (action) => {
              return _createVNode(_component_v_btn, {
                key: action.key,
                class: "run__act",
                variant: "outlined",
                size: "small",
                "prepend-icon": action.icon,
                disabled: workingNow.value,
                onClick: $event => (run(action))
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(action.label), 1)
                ]),
                _: 2
              }, 1032, ["prepend-icon", "disabled", "onClick"])
            }), 64))
          ])
        ])
      ]),
      _createElementVNode("div", _hoisted_12, [
        _createElementVNode("div", _hoisted_13, [
          _createElementVNode("div", null, [
            _cache[5] || (_cache[5] = _createElementVNode("h3", { class: "p115-section-title" }, "最近上传", -1)),
            _createElementVNode("p", _hoisted_14, "最新 " + _toDisplayString(visibleUploads.value.length) + " 部，标了「秒传」的没有实际耗流量。", 1)
          ])
        ]),
        _createElementVNode("div", _hoisted_15, [
          (visibleUploads.value.length)
            ? (_openBlock(), _createElementBlock("div", _hoisted_16, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(visibleUploads.value, (item) => {
                  return (_openBlock(), _createElementBlock("div", {
                    key: `${item.path}-${item.uploaded_at}`,
                    class: "card"
                  }, [
                    _createElementVNode("span", {
                      class: "card__name",
                      title: item.name
                    }, _toDisplayString(item.name), 9, _hoisted_17),
                    _createElementVNode("span", _hoisted_18, [
                      _createElementVNode("span", _hoisted_19, _toDisplayString(item.uploaded_at), 1),
                      _createElementVNode("span", {
                        class: _normalizeClass(["card__tag", { 'card__tag--instant': item.method === 'instant' }])
                      }, _toDisplayString(item.method === 'instant' ? '秒传' : '上传'), 3)
                    ])
                  ]))
                }), 128))
              ]))
            : (_openBlock(), _createElementBlock("p", _hoisted_20, "还没有上传记录。配好上传通道后跑一次全量上传就会出现在这里。"))
        ])
      ]),
      _createElementVNode("div", _hoisted_21, [
        _cache[6] || (_cache[6] = _createElementVNode("div", { class: "p115-panel__head" }, [
          _createElementVNode("div", null, [
            _createElementVNode("h3", { class: "p115-section-title" }, "执行记录"),
            _createElementVNode("p", { class: "p115-hint" }, "保留最近 50 次，最新的在最上面。")
          ])
        ], -1)),
        _createElementVNode("div", _hoisted_22, [
          (history.value.length)
            ? (_openBlock(), _createElementBlock("ul", _hoisted_23, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(history.value, (entry, index) => {
                  return (_openBlock(), _createElementBlock("li", {
                    key: `${entry.kind}-${entry.time}-${index}`,
                    class: "log__row"
                  }, [
                    _createElementVNode("span", _hoisted_24, _toDisplayString(kindNames[entry.kind] || entry.kind), 1),
                    _createElementVNode("span", _hoisted_25, _toDisplayString(entry.time || ''), 1),
                    _createElementVNode("span", _hoisted_26, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tally(entry), (text) => {
                        return (_openBlock(), _createElementBlock("span", {
                          key: text,
                          class: "log__chip"
                        }, _toDisplayString(text), 1))
                      }), 128))
                    ]),
                    (seconds(entry.duration_ms))
                      ? (_openBlock(), _createElementBlock("span", _hoisted_27, _toDisplayString(seconds(entry.duration_ms)), 1))
                      : _createCommentVNode("", true)
                  ]))
                }), 128))
              ]))
            : (_openBlock(), _createElementBlock("p", _hoisted_28, "还没有执行记录。跑一次任务后这里会记下每次的结果。"))
        ])
      ])
    ])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-b1b51fda"]]);

export { Page as default };
