import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, u as useHostNotice, A as AppBar, S as SITE_META, p as pluginGet, a as pluginPost } from './kit-34d2ba60.js';

// 签到台账的纯计算：日期归一、状态判定、连续天数、打卡带。
// 只吃 /status 返回的数据，不碰 DOM，也不引 Vue。

// 后端把这些状态视为「今天这枚卡打上了」
const SIGNED = new Set(['全部成功', '签到成功', '今日已签到']);

const pad = value => String(value).padStart(2, '0');

function dayKey(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function midnight(date = new Date()) {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy
}

// 后端时间是 'YYYY-MM-DD HH:MM:SS'，也可能是 '-' 或 '今天 ...'
function datePart(value, today = dayKey(new Date())) {
  if (!value) return ''
  const text = String(value);
  if (text.startsWith('今天')) return today
  const matched = text.match(/\d{4}-\d{2}-\d{2}/);
  return matched ? matched[0] : ''
}

function shortTime(value) {
  if (!value || value === '-') return '—'
  const matched = String(value).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return matched ? `${matched[2]}-${matched[3]} ${matched[4]}:${matched[5]}` : String(value)
}

// 一次执行落到哪一档：3 全签 / 2 部分 / 1 失败 / 0 无记录
function rankOf(status) {
  if (SIGNED.has(status)) return 3
  if (status === '部分成功') return 2
  if (status === '执行失败') return 1
  return 0
}

const RANK_WORD = { 3: '全部成功', 2: '部分成功', 1: '执行失败', 0: '没有记录' };

/**
 * 连续签到天数：从今天（今天还没签就从昨天）往回连数有成功记录的日子。
 */
function streakOf(history, now = new Date()) {
  const signed = new Set();
  for (const entry of history || []) {
    if (SIGNED.has(entry.status) || Number(entry.success_count) > 0) {
      const day = datePart(entry.time);
      if (day) signed.add(day);
    }
  }
  if (!signed.size) return 0

  const cursor = midnight(now);
  if (!signed.has(dayKey(cursor))) cursor.setDate(cursor.getDate() - 1);
  let days = 0;
  while (signed.has(dayKey(cursor))) {
    days += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return days
}

/**
 * 打卡带：最近 span 天，每天取当天最好的一档。返回从早到晚的格子。
 */
function tapeOf(history, span = 30, now = new Date()) {
  const best = {};
  for (const entry of history || []) {
    const day = datePart(entry.time);
    if (day) best[day] = Math.max(best[day] || 0, rankOf(entry.status));
  }

  const today = dayKey(midnight(now));
  const cells = [];
  for (let back = span - 1; back >= 0; back -= 1) {
    const cursor = midnight(now);
    cursor.setDate(cursor.getDate() - back);
    const day = dayKey(cursor);
    cells.push({
      day,
      label: day.slice(5),
      rank: best[day] || 0,
      today: day === today,
    });
  }
  return cells
}

/**
 * 今天这一格的结论，直接用来写标题。
 */
function todayVerdict(status = {}, now = new Date()) {
  const today = dayKey(midnight(now));
  const ranToday = datePart(status.last_run, today) === today;
  const total = Number(status.enabled_site_count) || 0;

  if (!ranToday) {
    return {
      rank: 0,
      headline: total ? '今天还没签' : '还没有启用站点',
      detail: total ? `${total} 个站点在等这一次执行` : '去配置页启用站点并填好账号',
    }
  }
  const rank = rankOf(status.last_status);
  const done = Number(status.last_result?.success_count) || 0;
  if (rank === 3) return { rank, headline: '今天已签完', detail: `${done} / ${total} 个站点签到成功` }
  if (rank === 2) return { rank, headline: '今天签了一半', detail: `${done} / ${total} 个站点成功，其余可以再跑一次` }
  return { rank, headline: '今天没签上', detail: status.last_result?.message || '看站点行的原因，处理后再跑一次' }
}

const Tape_vue_vue_type_style_index_0_scoped_e2265714_lang = '';

const {renderList:_renderList$1,Fragment:_Fragment$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,unref:_unref$1,createElementVNode:_createElementVNode$1,normalizeClass:_normalizeClass$1,createCommentVNode:_createCommentVNode$1,toDisplayString:_toDisplayString$1} = await importShared('vue');


const _hoisted_1$1 = { class: "tape" };
const _hoisted_2$1 = { class: "tape__run" };
const _hoisted_3$1 = ["disabled", "aria-label", "title"];
const _hoisted_4$1 = ["title"];
const _hoisted_5$1 = { class: "tape__scale ck-mono" };
const _hoisted_6$1 = { class: "tape__scale-mid" };

const {computed: computed$1} = await importShared('vue');


const _sfc_main$1 = {
  __name: 'Tape',
  props: {
  cells: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
},
  emits: ['punch'],
  setup(__props, { emit: __emit }) {

/**
 * 打卡带：最近 30 天，一天一格。今天那一格是真的按钮 —— 按下去就是签到，
 * 这个界面里唯一需要每天点一次的地方，就是记录本身。
 */
const props = __props;
const emit = __emit;

const RANK_CLASS = { 3: 'tape__cell--full', 2: 'tape__cell--part', 1: 'tape__cell--miss', 0: '' };

const first = computed$1(() => props.cells[0]?.label || '');
const last = computed$1(() => props.cells[props.cells.length - 1]?.label || '');
const signedDays = computed$1(() => props.cells.filter(cell => cell.rank === 3).length);

function title(cell) {
  return `${cell.day} · ${RANK_WORD[cell.rank]}`
}

return (_ctx, _cache) => {
  return (_openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
    _createElementVNode$1("ol", _hoisted_2$1, [
      (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(__props.cells, (cell) => {
        return (_openBlock$1(), _createElementBlock$1("li", {
          key: cell.day,
          class: _normalizeClass$1(["tape__slot", { 'tape__slot--today': cell.today }])
        }, [
          (cell.today)
            ? (_openBlock$1(), _createElementBlock$1("button", {
                key: 0,
                type: "button",
                class: _normalizeClass$1(["tape__cell tape__cell--today", [RANK_CLASS[cell.rank], { 'tape__cell--busy': __props.busy }]]),
                disabled: __props.disabled || __props.busy,
                "aria-label": __props.busy ? '正在签到' : `签到 ${cell.day}，当前${_unref$1(RANK_WORD)[cell.rank]}`,
                title: __props.busy ? '正在签到' : `${title(cell)} · 点击签到`,
                onClick: _cache[0] || (_cache[0] = $event => (emit('punch')))
              }, [...(_cache[1] || (_cache[1] = [
                _createElementVNode$1("span", {
                  class: "tape__today-hit",
                  "aria-hidden": "true"
                }, null, -1)
              ]))], 10, _hoisted_3$1))
            : (_openBlock$1(), _createElementBlock$1("span", {
                key: 1,
                class: _normalizeClass$1(["tape__cell", RANK_CLASS[cell.rank]]),
                title: title(cell)
              }, null, 10, _hoisted_4$1))
        ], 2))
      }), 128))
    ]),
    _createElementVNode$1("div", _hoisted_5$1, [
      _createElementVNode$1("span", null, _toDisplayString$1(first.value), 1),
      _createElementVNode$1("span", _hoisted_6$1, "30 天里签上 " + _toDisplayString$1(signedDays.value) + " 天", 1),
      _createElementVNode$1("span", null, _toDisplayString$1(last.value) + " 今天", 1)
    ])
  ]))
}
}

};
const Tape = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-e2265714"]]);

const Page_vue_vue_type_style_index_0_scoped_4b107ce2_lang = '';

const {createVNode:_createVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,unref:_unref,resolveComponent:_resolveComponent,withCtx:_withCtx,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "ck run" };
const _hoisted_2 = { class: "ck-sheet run__lede" };
const _hoisted_3 = { class: "lede__row" };
const _hoisted_4 = { class: "lede__fact ck-mono" };
const _hoisted_5 = { class: "lede__fact ck-mono" };
const _hoisted_6 = { class: "lede__fact ck-mono" };
const _hoisted_7 = { class: "lede__fact ck-mono" };
const _hoisted_8 = { class: "lede__acts" };
const _hoisted_9 = { class: "lede__note" };
const _hoisted_10 = { class: "ck-sheet" };
const _hoisted_11 = {
  key: 0,
  class: "sites"
};
const _hoisted_12 = {
  class: "site__badge ck-mono",
  "aria-hidden": "true"
};
const _hoisted_13 = { class: "site__id" };
const _hoisted_14 = { class: "site__name" };
const _hoisted_15 = { class: "site__acct ck-mono" };
const _hoisted_16 = { class: "site__tags" };
const _hoisted_17 = { class: "ck-chip" };
const _hoisted_18 = {
  key: 0,
  class: "ck-chip"
};
const _hoisted_19 = {
  key: 1,
  class: "ck-chip ck-chip--warn"
};
const _hoisted_20 = { class: "site__result" };
const _hoisted_21 = { class: "site__msg" };
const _hoisted_22 = { class: "site__when ck-mono" };
const _hoisted_23 = {
  key: 1,
  class: "ck-empty"
};
const _hoisted_24 = { class: "ck-sheet" };
const _hoisted_25 = { class: "ck-sheet__head" };
const _hoisted_26 = { class: "ck-hint" };
const _hoisted_27 = {
  key: 0,
  class: "log-grid"
};
const _hoisted_28 = ["open"];
const _hoisted_29 = { class: "log-card__sum" };
const _hoisted_30 = { class: "log-card__top" };
const _hoisted_31 = { class: "log-card__when ck-mono" };
const _hoisted_32 = { class: "log-card__score ck-mono" };
const _hoisted_33 = { class: "log-card__mid" };
const _hoisted_34 = { class: "log-card__msg" };
const _hoisted_35 = { class: "detail" };
const _hoisted_36 = { class: "detail__site" };
const _hoisted_37 = { class: "detail__msg" };
const _hoisted_38 = {
  key: 0,
  class: "detail__gain ck-mono"
};
const _hoisted_39 = {
  key: 1,
  class: "ck-empty"
};

const {computed,inject,onMounted,reactive,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: [Object, Function], default: null },
  show_switch: { type: Boolean, default: true },
},
  emits: ['switch', 'close', 'action'],
  setup(__props, { emit: __emit }) {

// 自用签到 · 台账页。视觉重做，接口契约不变：
// /status 拉状态、/run 立即签到、/test-login 测连通、/history/clear 清历史。
const props = __props;
const emit = __emit;

const status = ref({ sites: [], history: [] });
const busy = reactive({ load: false, run: false, test: false, clear: false });
const local = reactive({ text: '', kind: 'info' });
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text;
  local.kind = kind;
});

const history = computed(() => status.value.history || []);
// 执行记录：只显示最近 6 条（卡片式，节约空间）
const visibleHistory = computed(() => history.value.slice(0, 6));
const sites = computed(() => (status.value.sites || []).filter(site => site.enabled));
const verdict = computed(() => todayVerdict(status.value));
const streak = computed(() => streakOf(history.value));
const tape = computed(() => tapeOf(history.value, 30));

const TONE = { 3: 'on', 2: 'warn', 1: 'bad', 0: 'idle' };
const CHIP = { 3: 'ck-chip--on', 2: 'ck-chip--warn', 1: 'ck-chip--bad', 0: '' };

const barState = computed(() => {
  if (!status.value.enabled) return '未启用'
  if (!status.value.configured) return '配置待完善'
  return verdict.value.headline
});
const barTone = computed(() => {
  if (!status.value.enabled) return 'idle'
  if (!status.value.configured) return 'warn'
  return TONE[verdict.value.rank]
});

function chip(text) {
  return CHIP[rankOf(text)]
}

function badge(key) {
  return SITE_META[key]?.badge || '·'
}

async function refresh() {
  busy.load = true;
  try {
    status.value = await pluginGet(props.api, '/status');
  } catch (error) {
    notice.error(error?.message || '状态获取失败');
  } finally {
    busy.load = false;
  }
}

async function call(key, path, fallback) {
  busy[key] = true;
  try {
    const result = await pluginPost(props.api, path);
    if (result.success) notice.success(result.message || fallback);
    else notice.error(result.message || fallback);
    await refresh();
    emit('action');
  } catch (error) {
    notice.error(error?.message || fallback);
  } finally {
    busy[key] = false;
  }
}

const punch = () => call('run', '/run', '签到已执行');
const test = () => call('test', '/test-login', '连通性测试完成');

// 清空历史是危险操作：先确认再执行，防止误触
const clearConfirm = ref(false);
const wipe = () => {
  if (!clearConfirm.value) {
    clearConfirm.value = true;
    // 3 秒没二次点击就复位
    setTimeout(() => (clearConfirm.value = false), 3000);
    return
  }
  clearConfirm.value = false;
  call('clear', '/history/clear', '历史已清空');
};

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(AppBar, {
      view: "台账",
      state: barState.value,
      tone: barTone.value,
      "show-switch": __props.show_switch,
      busy: busy.load,
      "show-refresh": "",
      onRefresh: refresh,
      onSwitch: _cache[0] || (_cache[0] = $event => (emit('switch'))),
      onClose: _cache[1] || (_cache[1] = $event => (emit('close')))
    }, null, 8, ["state", "tone", "show-switch", "busy"]),
    (local.text)
      ? (_openBlock(), _createElementBlock("button", {
          key: 0,
          type: "button",
          class: _normalizeClass(["run__local", `run__local--${local.kind}`]),
          onClick: _cache[2] || (_cache[2] = $event => (local.text = ''))
        }, [
          _createTextVNode(_toDisplayString(local.text) + " ", 1),
          _cache[3] || (_cache[3] = _createElementVNode("span", { class: "run__local-x" }, "知道了", -1))
        ], 2))
      : _createCommentVNode("", true),
    _createElementVNode("section", _hoisted_2, [
      _createVNode(Tape, {
        cells: tape.value,
        busy: busy.run,
        disabled: !status.value.enabled,
        onPunch: punch
      }, null, 8, ["cells", "busy", "disabled"]),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("span", {
          class: _normalizeClass(["lede__tag", `lede__tag--${TONE[verdict.value.rank]}`])
        }, _toDisplayString(verdict.value.headline), 3),
        _createElementVNode("span", _hoisted_4, [
          _cache[4] || (_cache[4] = _createTextVNode(" 连续 ", -1)),
          _createElementVNode("strong", null, _toDisplayString(streak.value), 1),
          _cache[5] || (_cache[5] = _createTextVNode(" 天 ", -1))
        ]),
        _createElementVNode("span", _hoisted_5, [
          _cache[6] || (_cache[6] = _createTextVNode(" 下次 ", -1)),
          _createElementVNode("strong", null, _toDisplayString(status.value.next_run_time || '—'), 1)
        ]),
        _createElementVNode("span", _hoisted_6, [
          _cache[7] || (_cache[7] = _createTextVNode(" 上次 ", -1)),
          _createElementVNode("strong", null, _toDisplayString(_unref(shortTime)(status.value.last_run)), 1)
        ]),
        _createElementVNode("span", _hoisted_7, [
          _cache[8] || (_cache[8] = _createTextVNode(" 站点 ", -1)),
          _createElementVNode("strong", null, _toDisplayString(status.value.configured_site_count || 0) + " / " + _toDisplayString(status.value.enabled_site_count || 0), 1)
        ]),
        _createElementVNode("span", _hoisted_8, [
          _createVNode(_component_v_btn, {
            class: "ck-btn ck-btn--primary",
            variant: "flat",
            color: "primary",
            size: "small",
            loading: busy.run,
            disabled: !status.value.enabled,
            onClick: punch
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                start: "",
                icon: "mdi-calendar-check",
                size: "16"
              }),
              _cache[9] || (_cache[9] = _createTextVNode(" 签到 ", -1))
            ]),
            _: 1
          }, 8, ["loading", "disabled"]),
          _createVNode(_component_v_btn, {
            class: "ck-btn ck-btn--ghost",
            variant: "outlined",
            size: "small",
            loading: busy.test,
            onClick: test
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                start: "",
                icon: "mdi-connection",
                size: "16"
              }),
              _cache[10] || (_cache[10] = _createTextVNode(" 测试 ", -1))
            ]),
            _: 1
          }, 8, ["loading"]),
          _createVNode(_component_v_btn, {
            class: _normalizeClass(["ck-btn ck-btn--danger", { 'ck-btn--danger-confirm': clearConfirm.value }]),
            variant: "outlined",
            size: "small",
            loading: busy.clear,
            disabled: !history.value.length,
            onClick: wipe
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                start: "",
                icon: clearConfirm.value ? 'mdi-alert' : 'mdi-trash-can-outline',
                size: "16"
              }, null, 8, ["icon"]),
              _createTextVNode(" " + _toDisplayString(clearConfirm.value ? '确认清空？' : '清空'), 1)
            ]),
            _: 1
          }, 8, ["class", "loading", "disabled"])
        ])
      ]),
      _createElementVNode("p", _hoisted_9, _toDisplayString(verdict.value.detail), 1)
    ]),
    _createElementVNode("section", _hoisted_10, [
      _cache[11] || (_cache[11] = _createElementVNode("div", { class: "ck-sheet__head" }, [
        _createElementVNode("h3", { class: "ck-title" }, "站点"),
        _createElementVNode("p", { class: "ck-hint" }, "每行一个已启用的站点，写的是它上一次的结果。")
      ], -1)),
      (sites.value.length)
        ? (_openBlock(), _createElementBlock("ul", _hoisted_11, [
            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(sites.value, (site) => {
              return (_openBlock(), _createElementBlock("li", {
                key: site.key,
                class: "site"
              }, [
                _createElementVNode("span", _hoisted_12, _toDisplayString(badge(site.key)), 1),
                _createElementVNode("span", _hoisted_13, [
                  _createElementVNode("span", _hoisted_14, _toDisplayString(site.name), 1),
                  _createElementVNode("span", _hoisted_15, _toDisplayString(site.account || '未填账号'), 1)
                ]),
                _createElementVNode("span", _hoisted_16, [
                  _createElementVNode("span", _hoisted_17, _toDisplayString(site.mode), 1),
                  (site.use_proxy)
                    ? (_openBlock(), _createElementBlock("span", _hoisted_18, "代理"))
                    : _createCommentVNode("", true),
                  (!site.configured)
                    ? (_openBlock(), _createElementBlock("span", _hoisted_19, "待填写"))
                    : _createCommentVNode("", true)
                ]),
                _createElementVNode("span", _hoisted_20, [
                  _createElementVNode("span", {
                    class: _normalizeClass(["ck-chip", chip(site.last_status)])
                  }, _toDisplayString(site.last_status), 3),
                  _createElementVNode("span", _hoisted_21, _toDisplayString(site.last_message === '-' ? '' : site.last_message), 1)
                ]),
                _createElementVNode("span", _hoisted_22, _toDisplayString(_unref(shortTime)(site.last_run)), 1)
              ]))
            }), 128))
          ]))
        : (_openBlock(), _createElementBlock("p", _hoisted_23, "还没有启用站点。去设置里打开一个站点、填好账号，这里就会出现它的签到行。"))
    ]),
    _createElementVNode("section", _hoisted_24, [
      _createElementVNode("div", _hoisted_25, [
        _cache[12] || (_cache[12] = _createElementVNode("h3", { class: "ck-title" }, "执行记录", -1)),
        _createElementVNode("p", _hoisted_26, "保留最近 " + _toDisplayString(visibleHistory.value.length) + " 次，展开看每个站点当次的回复。", 1)
      ]),
      (visibleHistory.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_27, [
            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(visibleHistory.value, (entry, index) => {
              return (_openBlock(), _createElementBlock("details", {
                key: `${entry.time}-${index}`,
                class: "log-card",
                open: index === 0
              }, [
                _createElementVNode("summary", _hoisted_29, [
                  _createElementVNode("span", _hoisted_30, [
                    _createElementVNode("span", _hoisted_31, _toDisplayString(_unref(shortTime)(entry.time)), 1),
                    _createElementVNode("span", _hoisted_32, _toDisplayString(entry.success_count) + "/" + _toDisplayString(entry.site_count), 1)
                  ]),
                  _createElementVNode("span", _hoisted_33, [
                    _createElementVNode("span", {
                      class: _normalizeClass(["ck-chip", chip(entry.status)])
                    }, _toDisplayString(entry.status), 3),
                    _createElementVNode("span", _hoisted_34, _toDisplayString(entry.message), 1)
                  ])
                ]),
                _createElementVNode("ul", _hoisted_35, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(entry.details, (item, di) => {
                    return (_openBlock(), _createElementBlock("li", {
                      key: di,
                      class: "detail__row"
                    }, [
                      _createElementVNode("span", _hoisted_36, _toDisplayString(item.site_name), 1),
                      _createElementVNode("span", {
                        class: _normalizeClass(["ck-chip", chip(item.status)])
                      }, _toDisplayString(item.status), 3),
                      _createElementVNode("span", _hoisted_37, _toDisplayString(item.message), 1),
                      (item.reward_mb && item.reward_mb !== '-')
                        ? (_openBlock(), _createElementBlock("span", _hoisted_38, " +" + _toDisplayString(item.reward_mb), 1))
                        : _createCommentVNode("", true)
                    ]))
                  }), 128))
                ])
              ], 8, _hoisted_28))
            }), 128))
          ]))
        : (_openBlock(), _createElementBlock("p", _hoisted_39, "还没有执行记录。按一次「立即签到」，这里就会记下每个站点的回复。"))
    ])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-4b107ce2"]]);

export { Page as default };
