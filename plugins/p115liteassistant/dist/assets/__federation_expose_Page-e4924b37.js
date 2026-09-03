import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, u as useHostNotice, A as AppBar, p as pluginGet, a as pluginPost } from './kit-ab68ed17.js';

const Page_vue_vue_type_style_index_0_scoped_1d776b68_lang = '';

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
const _hoisted_12 = {
  key: 0,
  class: "p115-panel p115-panel--alert"
};
const _hoisted_13 = { class: "p115-panel__head" };
const _hoisted_14 = { class: "p115-hint p115-hint--warn" };
const _hoisted_15 = {
  key: 0,
  class: "pend__acts"
};
const _hoisted_16 = { class: "p115-panel__body" };
const _hoisted_17 = { class: "pend" };
const _hoisted_18 = { class: "pend__text" };
const _hoisted_19 = { class: "pend__mapping" };
const _hoisted_20 = { class: "pend__count p115-mono" };
const _hoisted_21 = {
  key: 0,
  class: "pend__when p115-mono"
};
const _hoisted_22 = {
  key: 1,
  class: "pend__when"
};
const _hoisted_23 = { class: "pend__acts" };
const _hoisted_24 = {
  key: 0,
  class: "pend-list"
};
const _hoisted_25 = {
  key: 0,
  class: "p115-hint"
};
const _hoisted_26 = {
  key: 0,
  class: "p115-hint"
};
const _hoisted_27 = {
  key: 1,
  class: "pend-list__more"
};
const _hoisted_28 = { class: "p115-hint" };
const _hoisted_29 = { class: "p115-panel" };
const _hoisted_30 = { class: "p115-panel__head" };
const _hoisted_31 = { class: "p115-hint" };
const _hoisted_32 = { class: "p115-panel__body" };
const _hoisted_33 = {
  key: 0,
  class: "card-grid"
};
const _hoisted_34 = ["title"];
const _hoisted_35 = { class: "card__meta" };
const _hoisted_36 = { class: "card__when p115-mono" };
const _hoisted_37 = {
  key: 1,
  class: "p115-empty"
};
const _hoisted_38 = { class: "p115-panel" };
const _hoisted_39 = { class: "p115-panel__head" };
const _hoisted_40 = { class: "p115-hint" };
const _hoisted_41 = { class: "p115-panel__body" };
const _hoisted_42 = {
  key: 0,
  class: "log-grid"
};
const _hoisted_43 = { class: "log-card__top" };
const _hoisted_44 = { class: "log-card__kind" };
const _hoisted_45 = {
  key: 0,
  class: "log-card__cost p115-mono"
};
const _hoisted_46 = { class: "log-card__when p115-mono" };
const _hoisted_47 = { class: "log-card__tally" };
const _hoisted_48 = {
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
// 执行记录：只显示最近 6 条（卡片式，节约空间）
const visibleHistory = computed(() => history.value.slice(0, 6));
const running = computed(() => status.value.running || []);
// strm / upload / sweep 共用同一把 115 数据任务锁，任何一个在跑其它都起不来
const workingNow = computed(() =>
  running.value.some(kind => kind === 'strm' || kind === 'upload' || kind === 'sweep'),
);

// 反向删除：先看有没有实时监听，没有就看开关，关着就直说
const sweepValue = computed(() => {
  if (!status.value.strm_delete_enabled) return '未启用'
  return status.value.strm_delete_watch_running ? '监听中' : '仅巡检'
});

const pendingDeletes = computed(() => status.value.pending_deletes || []);

const kindNames = { strm: '生成 STRM', upload: '上传', checkin: '签到', strm_sweep: '清理云端' };

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
  {
    key: 'sweep',
    label: '云端清理',
    value: sweepValue.value,
    ok: Boolean(status.value.strm_delete_enabled),
    hint: status.value.pending_sweep ? `${status.value.pending_sweep}排队中` : '',
  },
]);

const actions = [
  { key: 'strm', label: '生成 STRM', icon: 'mdi-file-link-outline', path: '/strm/sync', payload: {} },
  { key: 'full', label: '全量上传', icon: 'mdi-tray-arrow-up', path: '/upload', payload: { incremental: false } },
  { key: 'inc', label: '增量上传', icon: 'mdi-tray-plus', path: '/upload', payload: { incremental: true } },
  { key: 'sweep', label: '清理云端', icon: 'mdi-cloud-off-outline', path: '/strm/sweep', payload: {} },
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

const deciding = ref('');
const expanded = ref('');
const detail = reactive({ id: '', total: 0, items: [], loading: false });

// 待确认删除：确认就真删，驳回只丢清单。两个动作都要防连点。
async function decidePending(batchIds, approve) {
  const ids = [].concat(batchIds);
  if (deciding.value || !ids.length) return
  deciding.value = ids.length > 1 ? 'all' : ids[0];
  try {
    const path = approve ? '/strm/sweep/confirm' : '/strm/sweep/dismiss';
    const result = await pluginPost(props.api, path, { batch_ids: ids });
    if (result.success) notice.success(result.message || (approve ? '已开始清理云端' : '已忽略'));
    else notice.error(result.message || '操作未生效');
    if (ids.includes(expanded.value)) expanded.value = '';
    await refresh();
    emit('action');
  } catch (error) {
    notice.error(error?.message || '操作失败');
  } finally {
    deciding.value = '';
  }
}

// 删除前先看清单：整批的完整路径按页取，几百上千条也不至于一次灌进页面
async function loadDetail(batchId, append = false) {
  detail.loading = true;
  try {
    const offset = append ? detail.items.length : 0;
    const data = await pluginGet(props.api, '/strm/sweep/pending', { batch_id: batchId, offset, limit: 200 });
    const page = data?.data || data;
    detail.id = batchId;
    detail.total = Number(page?.total || 0);
    detail.items = append ? detail.items.concat(page?.items || []) : (page?.items || []);
  } catch (error) {
    notice.error(error?.message || '清单读取失败');
    detail.items = [];
  } finally {
    detail.loading = false;
  }
}

async function toggleDetail(batch) {
  if (expanded.value === batch.id) {
    expanded.value = '';
    return
  }
  expanded.value = batch.id;
  await loadDetail(batch.id);
}

const pendingTotal = computed(() =>
  pendingDeletes.value.reduce((sum, batch) => sum + Number(batch.count || 0), 0),
);
const pendingIds = computed(() => pendingDeletes.value.map(batch => batch.id));

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
  if (entry.kind === 'strm_sweep') {
    const parts = pick([['云端删除', 'cloud_deleted'], ['刮削', 'scrapes_deleted'], ['空目录', 'cloud_dirs_deleted'], ['待确认', 'pending'], ['云端已无', 'already_gone'], ['溯源缺失', 'unidentified'], ['失败', 'errors']]);
    if (parts.length) return parts
    return [entry.reason || '没有变化']
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
          _cache[5] || (_cache[5] = _createElementVNode("span", { class: "run__local-dismiss" }, "知道了", -1))
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
            _cache[6] || (_cache[6] = _createElementVNode("h3", { class: "p115-section-title" }, "手动跑一次", -1)),
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
      (pendingDeletes.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_12, [
            _createElementVNode("div", _hoisted_13, [
              _createElementVNode("div", null, [
                _cache[7] || (_cache[7] = _createElementVNode("h3", { class: "p115-section-title" }, "待确认删除", -1)),
                _createElementVNode("p", _hoisted_14, _toDisplayString(pendingDeletes.value.length) + " 批 · 共 " + _toDisplayString(pendingTotal.value) + " 个媒体。每批都要单独过一眼， 确认后才会真的删 115 上的文件（进回收站，可人工还原）。 ", 1)
              ]),
              (pendingDeletes.value.length > 1)
                ? (_openBlock(), _createElementBlock("div", _hoisted_15, [
                    _createVNode(_component_v_btn, {
                      variant: "text",
                      size: "small",
                      disabled: Boolean(deciding.value),
                      onClick: _cache[3] || (_cache[3] = $event => (decidePending(pendingIds.value, false)))
                    }, {
                      default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
                        _createTextVNode(" 全部忽略 ", -1)
                      ]))]),
                      _: 1
                    }, 8, ["disabled"]),
                    _createVNode(_component_v_btn, {
                      variant: "outlined",
                      size: "small",
                      color: "warning",
                      loading: deciding.value === 'all',
                      disabled: Boolean(deciding.value) || workingNow.value,
                      onClick: _cache[4] || (_cache[4] = $event => (decidePending(pendingIds.value, true)))
                    }, {
                      default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                        _createTextVNode(" 全部确认 ", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading", "disabled"])
                  ]))
                : _createCommentVNode("", true)
            ]),
            _createElementVNode("div", _hoisted_16, [
              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(pendingDeletes.value, (batch) => {
                return (_openBlock(), _createElementBlock("div", {
                  key: batch.id,
                  class: "pend-row"
                }, [
                  _createElementVNode("div", _hoisted_17, [
                    _createElementVNode("div", _hoisted_18, [
                      _createElementVNode("span", _hoisted_19, _toDisplayString(batch.mapping), 1),
                      _createElementVNode("span", _hoisted_20, _toDisplayString(batch.count) + " 个媒体", 1),
                      (batch.created_at)
                        ? (_openBlock(), _createElementBlock("span", _hoisted_21, _toDisplayString(batch.created_at), 1))
                        : _createCommentVNode("", true),
                      (batch.items_truncated)
                        ? (_openBlock(), _createElementBlock("span", _hoisted_22, "（清单已截断）"))
                        : _createCommentVNode("", true)
                    ]),
                    _createElementVNode("div", _hoisted_23, [
                      _createVNode(_component_v_btn, {
                        variant: "text",
                        size: "small",
                        "append-icon": expanded.value === batch.id ? 'mdi-chevron-up' : 'mdi-chevron-down',
                        onClick: $event => (toggleDetail(batch))
                      }, {
                        default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
                          _createTextVNode(" 查看清单 ", -1)
                        ]))]),
                        _: 1
                      }, 8, ["append-icon", "onClick"]),
                      _createVNode(_component_v_btn, {
                        variant: "text",
                        size: "small",
                        disabled: Boolean(deciding.value),
                        onClick: $event => (decidePending(batch.id, false))
                      }, {
                        default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
                          _createTextVNode(" 忽略 ", -1)
                        ]))]),
                        _: 1
                      }, 8, ["disabled", "onClick"]),
                      _createVNode(_component_v_btn, {
                        variant: "outlined",
                        size: "small",
                        color: "warning",
                        loading: deciding.value === batch.id,
                        disabled: Boolean(deciding.value) || workingNow.value,
                        onClick: $event => (decidePending(batch.id, true))
                      }, {
                        default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
                          _createTextVNode(" 确认删除 ", -1)
                        ]))]),
                        _: 1
                      }, 8, ["loading", "disabled", "onClick"])
                    ])
                  ]),
                  (expanded.value === batch.id)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_24, [
                        (detail.loading && !detail.items.length)
                          ? (_openBlock(), _createElementBlock("p", _hoisted_25, "读取清单中…"))
                          : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.items, (item) => {
                                return (_openBlock(), _createElementBlock("div", {
                                  key: item.path,
                                  class: "pend-list__row p115-mono"
                                }, _toDisplayString(item.cloud_path || item.path), 1))
                              }), 128)),
                              (!detail.items.length)
                                ? (_openBlock(), _createElementBlock("p", _hoisted_26, "清单为空。"))
                                : _createCommentVNode("", true),
                              (detail.items.length < detail.total)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_27, [
                                    _createElementVNode("span", _hoisted_28, "已显示 " + _toDisplayString(detail.items.length) + " / " + _toDisplayString(detail.total), 1),
                                    _createVNode(_component_v_btn, {
                                      variant: "text",
                                      size: "small",
                                      loading: detail.loading,
                                      onClick: $event => (loadDetail(batch.id, true))
                                    }, {
                                      default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
                                        _createTextVNode(" 加载更多 ", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["loading", "onClick"])
                                  ]))
                                : _createCommentVNode("", true)
                            ], 64))
                      ]))
                    : _createCommentVNode("", true)
                ]))
              }), 128))
            ])
          ]))
        : _createCommentVNode("", true),
      _createElementVNode("div", _hoisted_29, [
        _createElementVNode("div", _hoisted_30, [
          _createElementVNode("div", null, [
            _cache[14] || (_cache[14] = _createElementVNode("h3", { class: "p115-section-title" }, "最近上传", -1)),
            _createElementVNode("p", _hoisted_31, "最新 " + _toDisplayString(visibleUploads.value.length) + " 部，标了「秒传」的没有实际耗流量。", 1)
          ])
        ]),
        _createElementVNode("div", _hoisted_32, [
          (visibleUploads.value.length)
            ? (_openBlock(), _createElementBlock("div", _hoisted_33, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(visibleUploads.value, (item) => {
                  return (_openBlock(), _createElementBlock("div", {
                    key: `${item.path}-${item.uploaded_at}`,
                    class: "card"
                  }, [
                    _createElementVNode("span", {
                      class: "card__name",
                      title: item.name
                    }, _toDisplayString(item.name), 9, _hoisted_34),
                    _createElementVNode("span", _hoisted_35, [
                      _createElementVNode("span", _hoisted_36, _toDisplayString(item.uploaded_at), 1),
                      _createElementVNode("span", {
                        class: _normalizeClass(["card__tag", { 'card__tag--instant': item.method === 'instant' }])
                      }, _toDisplayString(item.method === 'instant' ? '秒传' : '上传'), 3)
                    ])
                  ]))
                }), 128))
              ]))
            : (_openBlock(), _createElementBlock("p", _hoisted_37, "还没有上传记录。配好上传通道后跑一次全量上传就会出现在这里。"))
        ])
      ]),
      _createElementVNode("div", _hoisted_38, [
        _createElementVNode("div", _hoisted_39, [
          _createElementVNode("div", null, [
            _cache[15] || (_cache[15] = _createElementVNode("h3", { class: "p115-section-title" }, "执行记录", -1)),
            _createElementVNode("p", _hoisted_40, "最近 " + _toDisplayString(visibleHistory.value.length) + " 条，最新的在最上面。", 1)
          ])
        ]),
        _createElementVNode("div", _hoisted_41, [
          (visibleHistory.value.length)
            ? (_openBlock(), _createElementBlock("div", _hoisted_42, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(visibleHistory.value, (entry, index) => {
                  return (_openBlock(), _createElementBlock("div", {
                    key: `${entry.kind}-${entry.time}-${index}`,
                    class: "log-card"
                  }, [
                    _createElementVNode("div", _hoisted_43, [
                      _createElementVNode("span", _hoisted_44, _toDisplayString(kindNames[entry.kind] || entry.kind), 1),
                      (seconds(entry.duration_ms))
                        ? (_openBlock(), _createElementBlock("span", _hoisted_45, _toDisplayString(seconds(entry.duration_ms)), 1))
                        : _createCommentVNode("", true)
                    ]),
                    _createElementVNode("div", _hoisted_46, _toDisplayString(entry.time || ''), 1),
                    _createElementVNode("div", _hoisted_47, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tally(entry), (text) => {
                        return (_openBlock(), _createElementBlock("span", {
                          key: text,
                          class: "log-card__chip"
                        }, _toDisplayString(text), 1))
                      }), 128))
                    ])
                  ]))
                }), 128))
              ]))
            : (_openBlock(), _createElementBlock("p", _hoisted_48, "还没有执行记录。跑一次任务后这里会记下每次的结果。"))
        ])
      ])
    ])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-1d776b68"]]);

export { Page as default };
