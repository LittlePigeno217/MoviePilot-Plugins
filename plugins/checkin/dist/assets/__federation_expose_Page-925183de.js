import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, S as SITE_META, p as pluginGet, a as pluginPost } from './_plugin-vue_export-helper-9f9119c5.js';

const Page_vue_vue_type_style_index_0_scoped_5113aee6_lang = '';

const {createElementVNode:_createElementVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,renderList:_renderList,Fragment:_Fragment,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createStaticVNode:_createStaticVNode} = await importShared('vue');


const _hoisted_1 = { class: "checkin-page" };
const _hoisted_2 = { class: "ck-masthead" };
const _hoisted_3 = { class: "ck-tools" };
const _hoisted_4 = ["disabled"];
const _hoisted_5 = { class: "ck-hero ck-panel" };
const _hoisted_6 = { class: "ck-hero__top" };
const _hoisted_7 = { class: "ck-almanac" };
const _hoisted_8 = { class: "ck-almanac__year" };
const _hoisted_9 = { class: "ck-almanac__day" };
const _hoisted_10 = { class: "ck-almanac__sub" };
const _hoisted_11 = { class: "ck-hero__center" };
const _hoisted_12 = { class: "ck-seal__text" };
const _hoisted_13 = { class: "ck-hero__sealsub" };
const _hoisted_14 = { class: "ck-streak" };
const _hoisted_15 = { class: "ck-streak__num" };
const _hoisted_16 = { class: "ck-streak__next" };
const _hoisted_17 = { class: "ck-actions" };
const _hoisted_18 = ["disabled"];
const _hoisted_19 = {
  key: 0,
  class: "ck-spin"
};
const _hoisted_20 = {
  key: 1,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  "stroke-width": "2",
  "stroke-linecap": "round",
  "stroke-linejoin": "round",
  width: "16",
  height: "16"
};
const _hoisted_21 = ["disabled"];
const _hoisted_22 = {
  key: 0,
  class: "ck-spin"
};
const _hoisted_23 = ["disabled"];
const _hoisted_24 = {
  key: 0,
  class: "ck-spin"
};
const _hoisted_25 = { class: "ck-ledger" };
const _hoisted_26 = { class: "ck-ledger__item" };
const _hoisted_27 = { class: "ck-ledger__item" };
const _hoisted_28 = { class: "ck-ledger__item" };
const _hoisted_29 = { class: "ck-ledger__v" };
const _hoisted_30 = { class: "ck-ledger__item" };
const _hoisted_31 = { class: "ck-ledger__v" };
const _hoisted_32 = { class: "ck-sites" };
const _hoisted_33 = { class: "ck-tile__head" };
const _hoisted_34 = { class: "ck-tile__name" };
const _hoisted_35 = { class: "ck-seal__text" };
const _hoisted_36 = { class: "ck-tile__mode" };
const _hoisted_37 = { class: "ck-chip ck-chip--muted" };
const _hoisted_38 = {
  key: 0,
  class: "ck-chip ck-chip--muted"
};
const _hoisted_39 = { class: "ck-tile__acct" };
const _hoisted_40 = { class: "ck-tile__foot" };
const _hoisted_41 = { class: "ck-tile__msg" };
const _hoisted_42 = {
  key: 1,
  class: "ck-empty ck-panel"
};
const _hoisted_43 = { class: "ck-history ck-panel" };
const _hoisted_44 = { class: "ck-history__head" };
const _hoisted_45 = { class: "ck-history__title" };
const _hoisted_46 = { class: "ck-history__count" };
const _hoisted_47 = {
  key: 0,
  class: "ck-heat",
  "aria-hidden": "true"
};
const _hoisted_48 = ["title"];
const _hoisted_49 = {
  key: 1,
  class: "ck-receipts"
};
const _hoisted_50 = ["open"];
const _hoisted_51 = { class: "ck-receipt__head" };
const _hoisted_52 = { class: "ck-receipt__date" };
const _hoisted_53 = { class: "ck-receipt__msg" };
const _hoisted_54 = { class: "ck-receipt__count" };
const _hoisted_55 = { class: "ck-receipt__body" };
const _hoisted_56 = { class: "ck-drow__site" };
const _hoisted_57 = { class: "ck-drow__acct" };
const _hoisted_58 = { class: "ck-drow__msg" };
const _hoisted_59 = {
  key: 0,
  class: "ck-drow__reward"
};
const _hoisted_60 = {
  key: 2,
  class: "ck-history__empty"
};

const {computed,onMounted,reactive,ref} = await importShared('vue');

const STEMS = '甲乙丙丁戊己庚辛壬癸';
const BRANCHES = '子丑寅卯辰巳午未申酉戌亥';
const CN_DIGITS = '〇一二三四五六七八九';

const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
  show_switch: { type: Boolean, default: true },
},
  emits: ['action', 'switch', 'close'],
  setup(__props, { emit: __emit }) {

// 自用签到 · 数据页（朱砂印章 · 每日一盖）
// 视觉重做，功能与后端契约不变：/status 拉取、/run 立即签到、/test-login 测试、/history/clear 清空。
const props = __props;
const emit = __emit;

const loading = ref(false);
const running = ref(false);
const testing = ref(false);
const clearing = ref(false);
const sealKey = ref(0); // 变化即重放印章「盖下」动画
const snackbar = reactive({ show: false, text: '', color: 'info' });
const status = ref({ sites: [], history: [] });

const enabledSites = computed(() => status.value.sites?.filter((s) => s.enabled) || []);
const history = computed(() => status.value.history || []);

// —— 黄历日期（公历 + 干支，纯计算，不依赖农历库）——
const CN_MONTH = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'];
const CN_WEEK = ['日', '一', '二', '三', '四', '五', '六'];
const pad = (n) => String(n).padStart(2, '0');
const now = new Date();
const todayStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
const today = {
  ganzhi: STEMS[(((now.getFullYear() - 4) % 10) + 10) % 10] + BRANCHES[(((now.getFullYear() - 4) % 12) + 12) % 12],
  cnYear: String(now.getFullYear()).split('').map((d) => CN_DIGITS[+d]).join(''),
  month: CN_MONTH[now.getMonth() + 1],
  day: now.getDate(),
  weekday: `星期${CN_WEEK[now.getDay()]}`,
};

const SUCCESS = new Set(['全部成功', '签到成功', '今日已签到']);
function datePart(s) {
  if (!s) return '';
  const str = String(s);
  if (str.startsWith('今天')) return todayStr;
  const m = str.match(/\d{4}-\d{2}-\d{2}/);
  return m ? m[0] : '';
}
function isToday(s) {
  return datePart(s) === todayStr;
}
function fmtTime(s) {
  if (!s || s === '-') return '-';
  const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : String(s);
}

// 今日主印状态
const heroSeal = computed(() => {
  const s = status.value;
  const signedToday = isToday(s.last_run);
  if (signedToday && SUCCESS.has(s.last_status)) return { state: 'success', label: '已签', sub: '今日已盖印' };
  if (signedToday && s.last_status === '部分成功') return { state: 'partial', label: '部分', sub: '今日部分完成' };
  if (signedToday && s.last_status === '执行失败') return { state: 'fail', label: '未成', sub: '今日执行失败' };
  return { state: 'pending', label: '待签', sub: s.last_run ? '今日尚未签到' : '等待首次签到' };
});
const sealMod = computed(() => ({
  success: '', partial: 'ck-seal--partial', fail: 'ck-seal--fail', pending: 'ck-seal--pending',
}[heroSeal.value.state]));
const sealStamps = computed(() => ['success', 'partial'].includes(heroSeal.value.state));

// 连续签到天数（从今日或最近一次签到日往回连数）
const streak = computed(() => {
  const signed = new Set();
  for (const e of history.value) {
    if (SUCCESS.has(e.status) || (e.success_count || 0) > 0) signed.add(datePart(e.time));
  }
  if (!signed.size) return 0;
  const key = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const cursor = new Date(now);
  cursor.setHours(0, 0, 0, 0);
  if (!signed.has(key(cursor))) cursor.setDate(cursor.getDate() - 1);
  let count = 0;
  while (signed.has(key(cursor))) {
    count += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return count;
});

// 近 21 天签到墙（每格取当日最好状态：成功>部分>失败>无）
const heat = computed(() => {
  const rankOf = (st) => (SUCCESS.has(st) ? 3 : st === '部分成功' ? 2 : st === '执行失败' ? 1 : 0);
  const map = {};
  for (const e of history.value) {
    const k = datePart(e.time);
    if (k) map[k] = Math.max(map[k] || 0, rankOf(e.status));
  }
  const cells = [];
  for (let i = 20; i >= 0; i -= 1) {
    const d = new Date(now);
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - i);
    const k = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    cells.push({ key: k, rank: map[k] || 0, today: k === todayStr });
  }
  return cells;
});

// 单站点迷你印
function siteSeal(st) {
  if (SUCCESS.has(st)) return { mod: '', label: '签' };
  if (st === '部分成功') return { mod: 'ck-seal--partial', label: '半' };
  if (st === '执行失败') return { mod: 'ck-seal--fail', label: '败' };
  return { mod: 'ck-seal--pending', label: '待' };
}
function chipClass(st) {
  if (SUCCESS.has(st)) return 'ck-chip--seal';
  if (st === '部分成功') return 'ck-chip--ochre';
  return 'ck-chip--muted';
}
function siteMode(key) {
  return SITE_META[key]?.mode || '';
}

function notify(text, color = 'info') {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

async function refresh() {
  loading.value = true;
  try {
    status.value = await pluginGet(props.api, '/status');
    sealKey.value += 1;
  } catch (error) {
    notify(error?.message || '状态获取失败', 'error');
  } finally {
    loading.value = false;
  }
}

async function runCheckin() {
  running.value = true;
  try {
    const result = await pluginPost(props.api, '/run');
    notify(result.message || '执行完成', result.success === false ? 'error' : 'success');
    await refresh();
    emit('action');
  } catch (error) {
    notify(error?.message || '执行失败', 'error');
  } finally {
    running.value = false;
  }
}

async function testLogin() {
  testing.value = true;
  try {
    const result = await pluginPost(props.api, '/test-login');
    notify(result.message || '测试完成', result.success === false ? 'error' : 'success');
  } catch (error) {
    notify(error?.message || '测试失败', 'error');
  } finally {
    testing.value = false;
  }
}

async function clearHistory() {
  clearing.value = true;
  try {
    const result = await pluginPost(props.api, '/history/clear');
    notify(result.message || '历史记录已清空', result.success === false ? 'error' : 'success');
    await refresh();
  } catch (error) {
    notify(error?.message || '清空失败', 'error');
  } finally {
    clearing.value = false;
  }
}

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("header", _hoisted_2, [
      _cache[6] || (_cache[6] = _createStaticVNode("<div class=\"ck-brand\" data-v-5113aee6><div class=\"ck-seal ck-brand__mark\" data-v-5113aee6><span class=\"ck-seal__text\" data-v-5113aee6>印</span></div><div data-v-5113aee6><div class=\"ck-brand__title\" data-v-5113aee6>自用签到</div><div class=\"ck-brand__sub\" data-v-5113aee6>每日一盖 · 站点签到墙</div></div></div>", 1)),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("button", {
          class: "ck-btn ck-btn--icon",
          title: "刷新",
          disabled: loading.value,
          onClick: refresh
        }, [
          (_openBlock(), _createElementBlock("svg", {
            class: _normalizeClass({ 'ck-spinning': loading.value }),
            viewBox: "0 0 24 24",
            fill: "none",
            stroke: "currentColor",
            "stroke-width": "2",
            "stroke-linecap": "round",
            "stroke-linejoin": "round"
          }, [...(_cache[3] || (_cache[3] = [
            _createElementVNode("path", { d: "M21 12a9 9 0 1 1-2.64-6.36" }, null, -1),
            _createElementVNode("path", { d: "M21 3v6h-6" }, null, -1)
          ]))], 2))
        ], 8, _hoisted_4),
        (__props.show_switch)
          ? (_openBlock(), _createElementBlock("button", {
              key: 0,
              class: "ck-btn ck-btn--icon",
              title: "配置",
              onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
            }, [...(_cache[4] || (_cache[4] = [
              _createElementVNode("svg", {
                viewBox: "0 0 24 24",
                fill: "none",
                stroke: "currentColor",
                "stroke-width": "2",
                "stroke-linecap": "round",
                "stroke-linejoin": "round"
              }, [
                _createElementVNode("circle", {
                  cx: "12",
                  cy: "12",
                  r: "3"
                }),
                _createElementVNode("path", { d: "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" })
              ], -1)
            ]))]))
          : _createCommentVNode("", true),
        _createElementVNode("button", {
          class: "ck-btn ck-btn--icon ck-btn--bare",
          title: "关闭",
          onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
        }, [...(_cache[5] || (_cache[5] = [
          _createElementVNode("svg", {
            viewBox: "0 0 24 24",
            fill: "none",
            stroke: "currentColor",
            "stroke-width": "2",
            "stroke-linecap": "round",
            "stroke-linejoin": "round"
          }, [
            _createElementVNode("path", { d: "M18 6 6 18M6 6l12 12" })
          ], -1)
        ]))])
      ])
    ]),
    _createElementVNode("section", _hoisted_5, [
      _createElementVNode("div", _hoisted_6, [
        _createElementVNode("div", _hoisted_7, [
          _createElementVNode("div", _hoisted_8, _toDisplayString(today.ganzhi) + "年 · " + _toDisplayString(today.cnYear), 1),
          _createElementVNode("div", _hoisted_9, _toDisplayString(today.day), 1),
          _createElementVNode("div", _hoisted_10, _toDisplayString(today.month) + "月 · " + _toDisplayString(today.weekday), 1),
          _cache[7] || (_cache[7] = _createElementVNode("div", { class: "ck-almanac__yi" }, [
            _createElementVNode("span", { class: "ck-yi" }, "宜"),
            _createTextVNode(" 签到")
          ], -1))
        ]),
        _createElementVNode("div", _hoisted_11, [
          (_openBlock(), _createElementBlock("div", {
            key: sealKey.value,
            class: _normalizeClass(["ck-seal ck-hero__seal", [sealMod.value, { 'ck-seal--stamp': sealStamps.value }]])
          }, [
            _createElementVNode("span", _hoisted_12, _toDisplayString(heroSeal.value.label), 1)
          ], 2)),
          _createElementVNode("div", _hoisted_13, _toDisplayString(heroSeal.value.sub), 1)
        ]),
        _createElementVNode("div", _hoisted_14, [
          _createElementVNode("div", _hoisted_15, _toDisplayString(streak.value), 1),
          _cache[9] || (_cache[9] = _createElementVNode("div", { class: "ck-streak__label" }, "连续签到 · 天", -1)),
          _createElementVNode("div", _hoisted_16, [
            _cache[8] || (_cache[8] = _createElementVNode("span", { class: "ck-streak__dot" }, null, -1)),
            _createTextVNode("下次 " + _toDisplayString(status.value.next_run_time || '未配置'), 1)
          ])
        ])
      ]),
      _createElementVNode("div", _hoisted_17, [
        _createElementVNode("button", {
          class: "ck-btn ck-btn--primary",
          disabled: running.value,
          onClick: runCheckin
        }, [
          (running.value)
            ? (_openBlock(), _createElementBlock("span", _hoisted_19))
            : (_openBlock(), _createElementBlock("svg", _hoisted_20, [...(_cache[10] || (_cache[10] = [
                _createElementVNode("circle", {
                  cx: "12",
                  cy: "12",
                  r: "9"
                }, null, -1),
                _createElementVNode("path", { d: "m9 12 2 2 4-4" }, null, -1)
              ]))])),
          _cache[11] || (_cache[11] = _createTextVNode(" 立即签到 ", -1))
        ], 8, _hoisted_18),
        _createElementVNode("button", {
          class: "ck-btn",
          disabled: testing.value,
          onClick: testLogin
        }, [
          (testing.value)
            ? (_openBlock(), _createElementBlock("span", _hoisted_22))
            : _createCommentVNode("", true),
          _cache[12] || (_cache[12] = _createTextVNode(" 测试登录 ", -1))
        ], 8, _hoisted_21),
        _createElementVNode("button", {
          class: "ck-btn ck-btn--danger",
          disabled: clearing.value,
          onClick: clearHistory
        }, [
          (clearing.value)
            ? (_openBlock(), _createElementBlock("span", _hoisted_24))
            : _createCommentVNode("", true),
          _cache[13] || (_cache[13] = _createTextVNode(" 清空历史 ", -1))
        ], 8, _hoisted_23)
      ]),
      _createElementVNode("div", _hoisted_25, [
        _createElementVNode("div", _hoisted_26, [
          _cache[14] || (_cache[14] = _createElementVNode("span", { class: "ck-ledger__k" }, "状态", -1)),
          _createElementVNode("span", {
            class: _normalizeClass(["ck-chip", status.value.enabled ? 'ck-chip--seal' : 'ck-chip--muted'])
          }, _toDisplayString(status.value.enabled ? '已启用' : '未启用'), 3)
        ]),
        _createElementVNode("div", _hoisted_27, [
          _cache[15] || (_cache[15] = _createElementVNode("span", { class: "ck-ledger__k" }, "配置", -1)),
          _createElementVNode("span", {
            class: _normalizeClass(["ck-chip", status.value.configured ? 'ck-chip--seal' : 'ck-chip--ochre'])
          }, _toDisplayString(status.value.configured ? '已完成' : '待完善'), 3)
        ]),
        _createElementVNode("div", _hoisted_28, [
          _cache[16] || (_cache[16] = _createElementVNode("span", { class: "ck-ledger__k" }, "启用站点", -1)),
          _createElementVNode("span", _hoisted_29, _toDisplayString(status.value.enabled_site_count || 0) + " / " + _toDisplayString(status.value.sites?.length || 0), 1)
        ]),
        _createElementVNode("div", _hoisted_30, [
          _cache[17] || (_cache[17] = _createElementVNode("span", { class: "ck-ledger__k" }, "最近执行", -1)),
          _createElementVNode("span", _hoisted_31, _toDisplayString(fmtTime(status.value.last_run)), 1)
        ])
      ])
    ]),
    _createElementVNode("section", _hoisted_32, [
      (enabledSites.value.length)
        ? (_openBlock(true), _createElementBlock(_Fragment, { key: 0 }, _renderList(enabledSites.value, (site) => {
            return (_openBlock(), _createElementBlock("article", {
              key: site.key,
              class: "ck-tile ck-panel"
            }, [
              _createElementVNode("div", _hoisted_33, [
                _createElementVNode("div", _hoisted_34, _toDisplayString(site.name), 1),
                _createElementVNode("div", {
                  class: _normalizeClass(["ck-seal ck-tile__seal", siteSeal(site.last_status).mod])
                }, [
                  _createElementVNode("span", _hoisted_35, _toDisplayString(siteSeal(site.last_status).label), 1)
                ], 2)
              ]),
              _createElementVNode("div", _hoisted_36, [
                _createElementVNode("span", _hoisted_37, _toDisplayString(site.mode || siteMode(site.key)), 1),
                (site.use_proxy)
                  ? (_openBlock(), _createElementBlock("span", _hoisted_38, "代理"))
                  : _createCommentVNode("", true)
              ]),
              _createElementVNode("div", _hoisted_39, _toDisplayString(site.account || '—'), 1),
              _createElementVNode("div", _hoisted_40, [
                _createElementVNode("span", {
                  class: _normalizeClass(["ck-chip", chipClass(site.last_status)])
                }, _toDisplayString(site.last_status || '未执行'), 3),
                _createElementVNode("span", _hoisted_41, _toDisplayString(site.last_message && site.last_message !== '-' ? site.last_message : ''), 1)
              ])
            ]))
          }), 128))
        : (_openBlock(), _createElementBlock("div", _hoisted_42, [...(_cache[18] || (_cache[18] = [
            _createElementVNode("div", { class: "ck-seal ck-seal--pending ck-empty__seal" }, [
              _createElementVNode("span", { class: "ck-seal__text" }, "待")
            ], -1),
            _createElementVNode("div", null, [
              _createElementVNode("div", { class: "ck-empty__title" }, "暂无启用站点"),
              _createElementVNode("div", { class: "ck-empty__sub" }, "前往配置页启用并填写站点账号")
            ], -1)
          ]))]))
    ]),
    _createElementVNode("section", _hoisted_43, [
      _createElementVNode("div", _hoisted_44, [
        _createElementVNode("div", _hoisted_45, [
          _cache[19] || (_cache[19] = _createTextVNode("签到历史", -1)),
          _createElementVNode("span", _hoisted_46, _toDisplayString(status.value.history_count || history.value.length) + " 次", 1)
        ])
      ]),
      (heat.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_47, [
            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(heat.value, (cell) => {
              return (_openBlock(), _createElementBlock("span", {
                key: cell.key,
                class: _normalizeClass(["ck-heat__cell", [`ck-heat__cell--${cell.rank}`, { 'ck-heat__cell--today': cell.today }]]),
                title: cell.key
              }, null, 10, _hoisted_48))
            }), 128))
          ]))
        : _createCommentVNode("", true),
      (history.value.length)
        ? (_openBlock(), _createElementBlock("div", _hoisted_49, [
            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(history.value, (entry, i) => {
              return (_openBlock(), _createElementBlock("details", {
                key: `${entry.time}-${i}`,
                class: "ck-receipt",
                open: i === 0
              }, [
                _createElementVNode("summary", _hoisted_51, [
                  _createElementVNode("span", _hoisted_52, _toDisplayString(fmtTime(entry.time)), 1),
                  _createElementVNode("span", _hoisted_53, _toDisplayString(entry.message || '—'), 1),
                  _createElementVNode("span", _hoisted_54, _toDisplayString(entry.success_count) + "/" + _toDisplayString(entry.site_count), 1),
                  _createElementVNode("span", {
                    class: _normalizeClass(["ck-chip", chipClass(entry.status)])
                  }, _toDisplayString(entry.status || '—'), 3),
                  _cache[20] || (_cache[20] = _createElementVNode("svg", {
                    class: "ck-receipt__chev",
                    viewBox: "0 0 24 24",
                    fill: "none",
                    stroke: "currentColor",
                    "stroke-width": "2",
                    "stroke-linecap": "round",
                    "stroke-linejoin": "round"
                  }, [
                    _createElementVNode("path", { d: "m9 18 6-6-6-6" })
                  ], -1))
                ]),
                _createElementVNode("div", _hoisted_55, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(entry.details, (d, di) => {
                    return (_openBlock(), _createElementBlock("div", {
                      key: di,
                      class: "ck-drow"
                    }, [
                      _createElementVNode("span", _hoisted_56, _toDisplayString(d.site_name || d.site), 1),
                      _createElementVNode("span", {
                        class: _normalizeClass(["ck-chip", chipClass(d.status)])
                      }, _toDisplayString(d.status), 3),
                      _createElementVNode("span", _hoisted_57, _toDisplayString(d.account), 1),
                      _createElementVNode("span", _hoisted_58, _toDisplayString(d.message), 1),
                      (d.reward_mb && d.reward_mb !== '-')
                        ? (_openBlock(), _createElementBlock("span", _hoisted_59, "+" + _toDisplayString(d.reward_mb), 1))
                        : _createCommentVNode("", true)
                    ]))
                  }), 128))
                ])
              ], 8, _hoisted_50))
            }), 128))
          ]))
        : (_openBlock(), _createElementBlock("div", _hoisted_60, "暂无签到记录，今日盖下第一枚印。"))
    ]),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((snackbar.show) = $event)),
      color: snackbar.color,
      timeout: "3000",
      location: "bottom"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(snackbar.text), 1)
      ]),
      _: 1
    }, 8, ["modelValue", "color"])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-5113aee6"]]);

export { Page as default };
