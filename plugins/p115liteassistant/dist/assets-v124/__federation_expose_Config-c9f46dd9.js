import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginGet, N as NOTIFY_TYPES, a as pluginPost, n as normalizeConfig, u as useHostNotice, A as AppBar, c as clone, b as newId } from './kit-a6d4b6ea.js';

const Conduit_vue_vue_type_style_index_0_scoped_1ac6f414_lang = '';

const {resolveComponent:_resolveComponent$4,createVNode:_createVNode$4,toDisplayString:_toDisplayString$4,createElementVNode:_createElementVNode$4,renderList:_renderList$3,Fragment:_Fragment$3,openBlock:_openBlock$4,createElementBlock:_createElementBlock$4,createCommentVNode:_createCommentVNode$4,createTextVNode:_createTextVNode$3,normalizeClass:_normalizeClass$1} = await importShared('vue');


const _hoisted_1$4 = { class: "conduit__bar" };
const _hoisted_2$4 = { class: "conduit__ordinal p115-mono" };
const _hoisted_3$4 = { class: "conduit__track" };
const _hoisted_4$3 = {
  key: 0,
  class: "conduit__flow",
  "aria-hidden": "true"
};
const _hoisted_5$3 = ["onClick"];
const _hoisted_6$3 = { class: "conduit__stop-tag" };
const _hoisted_7$3 = {
  key: 0,
  class: "conduit__stop-path p115-mono"
};
const _hoisted_8$3 = {
  key: 1,
  class: "conduit__stop-path conduit__stop-path--empty"
};

const {computed: computed$4} = await importShared('vue');



const _sfc_main$4 = {
  __name: 'Conduit',
  props: {
  enabled: { type: Boolean, default: true },
  stops: { type: Array, default: () => [] },
  index: { type: Number, default: 0 },
},
  emits: ['update:enabled', 'pick', 'remove'],
  setup(__props, { emit: __emit }) {

/**
 * 通道（Conduit）—— 本插件的签名元素。
 *
 * 插件做的每件事都是一次“搬运”：115 的某个目录 → 本地某个目录。与其把它拆成
 * 两个互不相干的输入框，这里把一条映射画成一条真实的通道：左端是起点，右端是
 * 终点，中间是带方向的管线。通道亮起代表这条映射启用，熄灭代表停用——开关的
 * 状态因此不需要额外文字解释。
 */
const props = __props;
const emit = __emit;

const live = computed$4(() => props.enabled);

return (_ctx, _cache) => {
  const _component_v_switch = _resolveComponent$4("v-switch");
  const _component_v_spacer = _resolveComponent$4("v-spacer");
  const _component_v_btn = _resolveComponent$4("v-btn");
  const _component_v_icon = _resolveComponent$4("v-icon");

  return (_openBlock$4(), _createElementBlock$4("div", {
    class: _normalizeClass$1(["conduit", { 'conduit--live': live.value }])
  }, [
    _createElementVNode$4("div", _hoisted_1$4, [
      _createVNode$4(_component_v_switch, {
        "model-value": __props.enabled,
        color: "primary",
        density: "compact",
        "hide-details": "",
        "aria-label": __props.enabled ? '停用这条通道' : '启用这条通道',
        "onUpdate:modelValue": _cache[0] || (_cache[0] = value => emit('update:enabled', Boolean(value)))
      }, null, 8, ["model-value", "aria-label"]),
      _createElementVNode$4("span", _hoisted_2$4, "通道 " + _toDisplayString$4(__props.index + 1), 1),
      _createVNode$4(_component_v_spacer),
      _createVNode$4(_component_v_btn, {
        icon: "mdi-close",
        variant: "text",
        size: "x-small",
        "aria-label": "删除这条通道",
        onClick: _cache[1] || (_cache[1] = $event => (emit('remove')))
      })
    ]),
    _createElementVNode$4("div", _hoisted_3$4, [
      (_openBlock$4(true), _createElementBlock$4(_Fragment$3, null, _renderList$3(__props.stops, (stop, position) => {
        return (_openBlock$4(), _createElementBlock$4(_Fragment$3, {
          key: stop.key
        }, [
          position
            ? (_openBlock$4(), _createElementBlock$4("span", _hoisted_4$3, [
                _cache[2] || (_cache[2] = _createElementVNode$4("span", { class: "conduit__flow-line" }, null, -1)),
                _createVNode$4(_component_v_icon, {
                  icon: "mdi-chevron-right",
                  size: "16",
                  class: "conduit__flow-head"
                })
              ]))
            : _createCommentVNode$4("", true),
          _createElementVNode$4("button", {
            type: "button",
            class: "conduit__stop",
            onClick: $event => (emit('pick', stop.key))
          }, [
            _createElementVNode$4("span", _hoisted_6$3, [
              _createVNode$4(_component_v_icon, {
                icon: stop.icon,
                size: "13"
              }, null, 8, ["icon"]),
              _createTextVNode$3(" " + _toDisplayString$4(stop.tag), 1)
            ]),
            (stop.value)
              ? (_openBlock$4(), _createElementBlock$4("span", _hoisted_7$3, _toDisplayString$4(stop.value), 1))
              : (_openBlock$4(), _createElementBlock$4("span", _hoisted_8$3, _toDisplayString$4(stop.placeholder), 1))
          ], 8, _hoisted_5$3)
        ], 64))
      }), 128))
    ])
  ], 2))
}
}

};
const Conduit = /*#__PURE__*/_export_sfc(_sfc_main$4, [['__scopeId',"data-v-1ac6f414"]]);

const DirPicker_vue_vue_type_style_index_0_scoped_753346c2_lang = '';

const {toDisplayString:_toDisplayString$3,createElementVNode:_createElementVNode$3,resolveComponent:_resolveComponent$3,createVNode:_createVNode$3,openBlock:_openBlock$3,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$3,createElementBlock:_createElementBlock$3,renderList:_renderList$2,Fragment:_Fragment$2,withCtx:_withCtx$2,createTextVNode:_createTextVNode$2} = await importShared('vue');


const _hoisted_1$3 = { class: "picker__head" };
const _hoisted_2$3 = { class: "p115-endpoint-tag" };
const _hoisted_3$3 = { class: "picker__title" };
const _hoisted_4$2 = { class: "picker__here" };
const _hoisted_5$2 = { class: "picker__path p115-mono" };
const _hoisted_6$2 = {
  key: 1,
  class: "picker__failed"
};
const _hoisted_7$2 = {
  key: 3,
  class: "p115-empty"
};
const _hoisted_8$2 = { class: "picker__foot" };

const {computed: computed$3,reactive: reactive$2,ref: ref$2,watch: watch$2} = await importShared('vue');


const _sfc_main$3 = {
  __name: 'DirPicker',
  props: {
  modelValue: { type: Boolean, default: false },
  api: { type: [Object, Function], default: null },
  remote: { type: Boolean, default: false },
  title: { type: String, default: '选择目录' },
},
  emits: ['update:modelValue', 'select', 'error'],
  setup(__props, { emit: __emit }) {

/**
 * 目录选择器。远端浏览 115（按 cid 逐层下钻），本地浏览 MoviePilot 可见目录
 * （按相对路径下钻）。选中当前所在目录后回传，由调用方决定写进哪个字段。
 */
const props = __props;
const emit = __emit;

const cid = ref$2('0');
const trail = ref$2([]);
const path = ref$2('');
const localBase = ref$2('');
const roots = ref$2([]);
const items = ref$2([]);
const loading = ref$2(false);
const state = reactive$2({ failed: '' });

const remotePath = computed$3(() => {
  const joined = trail.value.map(stop => stop.name).join('/');
  return joined ? `/${joined}` : '/'
});
const localPath = computed$3(() => {
  const base = localBase.value.replace(/[\\/]+$/, '');
  return path.value ? `${base}/${path.value}` : base || '/'
});
const here = computed$3(() => (props.remote ? remotePath.value : localPath.value));
const canAscend = computed$3(() => (props.remote ? trail.value.length > 0 : Boolean(path.value)));

async function load(step) {
  loading.value = true;
  state.failed = '';
  try {
    if (props.remote) {
      if (step) {
        trail.value.push({ cid: cid.value, name: step.name });
        cid.value = step.cid;
      }
      const data = await pluginGet(props.api, '/browse-115', { cid: cid.value });
      if (data.error) throw new Error(data.error)
      items.value = data.items || [];
    } else {
      if (step) path.value = step.path;
      const data = await pluginGet(props.api, '/browse-local', { path: path.value, root: localBase.value });
      if (data.error) throw new Error(data.error)
      localBase.value = data.base || localBase.value;
      roots.value = data.roots || roots.value;
      path.value = data.current || '';
      items.value = data.items || [];
    }
  } catch (error) {
    state.failed = error?.message || '目录读取失败';
    emit('error', state.failed);
  } finally {
    loading.value = false;
  }
}

async function ascend() {
  if (!canAscend.value) return
  if (props.remote) {
    const previous = trail.value.pop();
    if (!previous) return
    cid.value = previous.cid;
  } else {
    path.value = path.value.split('/').slice(0, -1).join('/');
  }
  await load();
}

async function switchRoot(root) {
  localBase.value = root || '';
  path.value = '';
  await load();
}

function confirm() {
  emit('select', props.remote ? { cid: cid.value, path: remotePath.value } : { path: localPath.value });
  emit('update:modelValue', false);
}

watch$2(
  () => props.modelValue,
  async open => {
    if (!open) return
    cid.value = '0';
    trail.value = [];
    path.value = '';
    localBase.value = '';
    roots.value = [];
    items.value = [];
    await load();
  },
);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$3("v-btn");
  const _component_v_select = _resolveComponent$3("v-select");
  const _component_v_progress_linear = _resolveComponent$3("v-progress-linear");
  const _component_v_list_item = _resolveComponent$3("v-list-item");
  const _component_v_list = _resolveComponent$3("v-list");
  const _component_v_card_text = _resolveComponent$3("v-card-text");
  const _component_v_card = _resolveComponent$3("v-card");
  const _component_v_dialog = _resolveComponent$3("v-dialog");

  return (_openBlock$3(), _createBlock$2(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": "620",
    scrollable: "",
    "onUpdate:modelValue": _cache[2] || (_cache[2] = value => emit('update:modelValue', value))
  }, {
    default: _withCtx$2(() => [
      _createVNode$3(_component_v_card, { class: "picker p115-portal" }, {
        default: _withCtx$2(() => [
          _createElementVNode$3("div", _hoisted_1$3, [
            _createElementVNode$3("div", null, [
              _createElementVNode$3("div", _hoisted_2$3, _toDisplayString$3(__props.remote ? '115 云端' : 'MOVIEPILOT 本地'), 1),
              _createElementVNode$3("h2", _hoisted_3$3, _toDisplayString$3(__props.title), 1)
            ]),
            _createVNode$3(_component_v_btn, {
              icon: "mdi-close",
              variant: "text",
              size: "small",
              "aria-label": "关闭",
              onClick: _cache[0] || (_cache[0] = $event => (emit('update:modelValue', false)))
            })
          ]),
          _createElementVNode$3("div", _hoisted_4$2, [
            _createVNode$3(_component_v_btn, {
              icon: "mdi-arrow-up",
              variant: "text",
              size: "x-small",
              disabled: !canAscend.value,
              "aria-label": "回到上一级",
              onClick: ascend
            }, null, 8, ["disabled"]),
            _createElementVNode$3("span", _hoisted_5$2, _toDisplayString$3(here.value), 1)
          ]),
          (!__props.remote && roots.value.length > 1)
            ? (_openBlock$3(), _createBlock$2(_component_v_select, {
                key: 0,
                "model-value": localBase.value,
                items: roots.value,
                "item-title": "name",
                "item-value": "path",
                label: "根目录",
                variant: "outlined",
                density: "compact",
                "hide-details": "",
                class: "mx-4 mb-3",
                "onUpdate:modelValue": switchRoot
              }, null, 8, ["model-value", "items"]))
            : _createCommentVNode$3("", true),
          _createVNode$3(_component_v_card_text, { class: "picker__list" }, {
            default: _withCtx$2(() => [
              (loading.value)
                ? (_openBlock$3(), _createBlock$2(_component_v_progress_linear, {
                    key: 0,
                    indeterminate: "",
                    color: "primary"
                  }))
                : _createCommentVNode$3("", true),
              (state.failed)
                ? (_openBlock$3(), _createElementBlock$3("p", _hoisted_6$2, _toDisplayString$3(state.failed), 1))
                : (items.value.length)
                  ? (_openBlock$3(), _createBlock$2(_component_v_list, {
                      key: 2,
                      density: "compact",
                      lines: "one",
                      "bg-color": "transparent"
                    }, {
                      default: _withCtx$2(() => [
                        (_openBlock$3(true), _createElementBlock$3(_Fragment$2, null, _renderList$2(items.value, (item) => {
                          return (_openBlock$3(), _createBlock$2(_component_v_list_item, {
                            key: item.cid || item.path,
                            "prepend-icon": "mdi-folder-outline",
                            title: item.name,
                            onClick: $event => (load(item))
                          }, null, 8, ["title", "onClick"]))
                        }), 128))
                      ]),
                      _: 1
                    }))
                  : (!loading.value)
                    ? (_openBlock$3(), _createElementBlock$3("p", _hoisted_7$2, "这一层没有子目录，可直接选它。"))
                    : _createCommentVNode$3("", true)
            ]),
            _: 1
          }),
          _createElementVNode$3("div", _hoisted_8$2, [
            _createVNode$3(_component_v_btn, {
              variant: "text",
              size: "small",
              onClick: _cache[1] || (_cache[1] = $event => (emit('update:modelValue', false)))
            }, {
              default: _withCtx$2(() => [...(_cache[3] || (_cache[3] = [
                _createTextVNode$2("取消", -1)
              ]))]),
              _: 1
            }),
            _createVNode$3(_component_v_btn, {
              color: "primary",
              variant: "flat",
              size: "small",
              disabled: loading.value,
              onClick: confirm
            }, {
              default: _withCtx$2(() => [...(_cache[4] || (_cache[4] = [
                _createTextVNode$2(" 选用当前目录 ", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"])
          ])
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["model-value"]))
}
}

};
const DirPicker = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-753346c2"]]);

const NotifyRow_vue_vue_type_style_index_0_scoped_b8cb2d38_lang = '';

const {resolveComponent:_resolveComponent$2,createVNode:_createVNode$2,createElementVNode:_createElementVNode$2,toDisplayString:_toDisplayString$2,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createCommentVNode:_createCommentVNode$2} = await importShared('vue');


const _hoisted_1$2 = { class: "ntf" };
const _hoisted_2$2 = { class: "ntf__line" };
const _hoisted_3$2 = {
  key: 0,
  class: "p115-hint"
};

const {computed: computed$2} = await importShared('vue');


const _sfc_main$2 = {
  __name: 'NotifyRow',
  props: {
  enabled: { type: Boolean, default: false },
  type: { type: String, default: 'Plugin' },
  label: { type: String, default: '执行后发送通知' },
  hint: { type: String, default: '' },
  types: { type: Array, default: null },
},
  emits: ['update:enabled', 'update:type'],
  setup(__props, { emit: __emit }) {

/**
 * 通道通知开关。一条通道一个实例，开关和消息类型都是独立字段——
 * STRM 只关心自己的，签到失败不会因为上传没开通知而静默。
 * 消息类型下拉优先用宿主注入的动态列表（types prop，来自 MoviePilot MessageType 源，
 * 与渠道 switchs 分流中文 value 同步），没有才回退到静态 NOTIFY_TYPES。
 */
const props = __props;
const emit = __emit;

const typeOptions = computed$2(
  () => (Array.isArray(props.types) && props.types.length ? props.types : NOTIFY_TYPES)
);

return (_ctx, _cache) => {
  const _component_v_switch = _resolveComponent$2("v-switch");
  const _component_v_select = _resolveComponent$2("v-select");

  return (_openBlock$2(), _createElementBlock$2("div", _hoisted_1$2, [
    _createElementVNode$2("div", _hoisted_2$2, [
      _createVNode$2(_component_v_switch, {
        "model-value": props.enabled,
        color: "primary",
        density: "compact",
        "hide-details": "",
        label: props.label,
        "onUpdate:modelValue": _cache[0] || (_cache[0] = value => emit('update:enabled', Boolean(value)))
      }, null, 8, ["model-value", "label"]),
      _createVNode$2(_component_v_select, {
        "model-value": props.type,
        items: typeOptions.value,
        disabled: !props.enabled,
        class: "ntf__type",
        label: "消息类型",
        variant: "outlined",
        density: "compact",
        "hide-details": "",
        "onUpdate:modelValue": _cache[1] || (_cache[1] = value => emit('update:type', value))
      }, null, 8, ["model-value", "items", "disabled"])
    ]),
    (props.hint)
      ? (_openBlock$2(), _createElementBlock$2("p", _hoisted_3$2, _toDisplayString$2(props.hint), 1))
      : _createCommentVNode$2("", true)
  ]))
}
}

};
const NotifyRow = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-b8cb2d38"]]);

const QrLogin_vue_vue_type_style_index_0_scoped_fb3a5ece_lang = '';

const {createElementVNode:_createElementVNode$1,resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,renderList:_renderList$1,Fragment:_Fragment$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$1,withCtx:_withCtx$1,createCommentVNode:_createCommentVNode$1,createBlock:_createBlock$1} = await importShared('vue');


const _hoisted_1$1 = { class: "qr__head" };
const _hoisted_2$1 = {
  class: "qr__clients",
  role: "group",
  "aria-label": "选择扫码客户端"
};
const _hoisted_3$1 = { class: "qr__stage" };
const _hoisted_4$1 = {
  key: 0,
  class: "qr__pending"
};
const _hoisted_5$1 = ["src"];
const _hoisted_6$1 = {
  key: 2,
  class: "qr__pending p115-muted"
};
const _hoisted_7$1 = {
  key: 0,
  class: "qr__failed"
};
const _hoisted_8$1 = {
  key: 1,
  class: "qr__step"
};
const _hoisted_9$1 = { class: "qr__foot" };

const {computed: computed$1,onBeforeUnmount,reactive: reactive$1,ref: ref$1,watch: watch$1} = await importShared('vue');


const _sfc_main$1 = {
  __name: 'QrLogin',
  props: {
  modelValue: { type: Boolean, default: false },
  api: { type: [Object, Function], default: null },
},
  emits: ['update:modelValue', 'authenticated', 'error'],
  setup(__props, { emit: __emit }) {

/**
 * 115 扫码登录。轮询 /check-login，成功后由调用方重新拉取配置拿到 Cookie。
 */
const props = __props;
const emit = __emit;

const clients = [
  { label: '支付宝', value: 'alipaymini' },
  { label: '微信', value: 'wechatmini' },
  { label: '安卓', value: '115android' },
  { label: 'iOS', value: '115ios' },
  { label: '网页', value: 'web' },
  { label: 'PAD', value: '115ipad' },
  { label: 'TV', value: 'tv' },
];

const state = reactive$1({ loading: false, failed: '', code: '', client: 'alipaymini', step: '等待扫码' });
const timer = ref$1(null);
const activeClient = computed$1(() => clients.find(item => item.value === state.client) || clients[0]);

function stopPolling() {
  if (timer.value) {
    clearInterval(timer.value);
    timer.value = null;
  }
}

async function poll() {
  try {
    const data = await pluginGet(props.api, '/check-login');
    const code = Number(data.status);
    if (code === 2) {
      stopPolling();
      state.step = '登录成功';
      emit('authenticated');
      emit('update:modelValue', false);
    } else if (code === 1) {
      state.step = '已扫码，请在设备上确认';
    } else if (code === -1 || code === -2) {
      stopPolling();
      state.failed = data.tip || (code === -1 ? '二维码已过期，请刷新' : '登录已取消');
    } else {
      state.step = data.tip || '等待扫码';
    }
  } catch (error) {
    stopPolling();
    state.failed = error?.message || '登录状态检查失败';
  }
}

async function issue() {
  stopPolling();
  state.loading = true;
  state.failed = '';
  state.code = '';
  state.step = '正在获取二维码';
  try {
    const result = await pluginPost(props.api, '/qrcode', { client_type: state.client });
    if (!result.success || !result.data?.qrcode) throw new Error(result.message || '115 未返回二维码')
    state.code = result.data.qrcode;
    state.client = result.data.client_type || state.client;
    state.step = '等待扫码';
    timer.value = window.setInterval(poll, 3000);
  } catch (error) {
    state.failed = error?.message || '获取二维码失败';
    emit('error', state.failed);
  } finally {
    state.loading = false;
  }
}

async function useClient(value) {
  if (value === state.client) return
  state.client = value;
  await issue();
}

watch$1(
  () => props.modelValue,
  async open => {
    if (open) await issue();
    else stopPolling();
  },
);
onBeforeUnmount(stopPolling);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_progress_circular = _resolveComponent$1("v-progress-circular");
  const _component_v_card_text = _resolveComponent$1("v-card-text");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_dialog = _resolveComponent$1("v-dialog");

  return (_openBlock$1(), _createBlock$1(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": "420",
    "onUpdate:modelValue": _cache[2] || (_cache[2] = value => emit('update:modelValue', value))
  }, {
    default: _withCtx$1(() => [
      _createVNode$1(_component_v_card, { class: "qr p115-portal" }, {
        default: _withCtx$1(() => [
          _createElementVNode$1("div", _hoisted_1$1, [
            _cache[3] || (_cache[3] = _createElementVNode$1("div", null, [
              _createElementVNode$1("div", { class: "p115-endpoint-tag" }, "115 授权"),
              _createElementVNode$1("h2", { class: "qr__title" }, "扫码登录")
            ], -1)),
            _createVNode$1(_component_v_btn, {
              icon: "mdi-close",
              variant: "text",
              size: "small",
              "aria-label": "关闭",
              onClick: _cache[0] || (_cache[0] = $event => (emit('update:modelValue', false)))
            })
          ]),
          _createVNode$1(_component_v_card_text, { class: "qr__body" }, {
            default: _withCtx$1(() => [
              _createElementVNode$1("div", _hoisted_2$1, [
                (_openBlock$1(), _createElementBlock$1(_Fragment$1, null, _renderList$1(clients, (client) => {
                  return _createVNode$1(_component_v_btn, {
                    key: client.value,
                    size: "x-small",
                    variant: state.client === client.value ? 'flat' : 'outlined',
                    color: state.client === client.value ? 'primary' : undefined,
                    onClick: $event => (useClient(client.value))
                  }, {
                    default: _withCtx$1(() => [
                      _createTextVNode$1(_toDisplayString$1(client.label), 1)
                    ]),
                    _: 2
                  }, 1032, ["variant", "color", "onClick"])
                }), 64))
              ]),
              _createElementVNode$1("div", _hoisted_3$1, [
                (state.loading)
                  ? (_openBlock$1(), _createElementBlock$1("div", _hoisted_4$1, [
                      _createVNode$1(_component_v_progress_circular, {
                        indeterminate: "",
                        color: "primary",
                        size: "34"
                      })
                    ]))
                  : (state.code)
                    ? (_openBlock$1(), _createElementBlock$1("img", {
                        key: 1,
                        src: state.code,
                        alt: "115 登录二维码",
                        class: "qr__code"
                      }, null, 8, _hoisted_5$1))
                    : (_openBlock$1(), _createElementBlock$1("div", _hoisted_6$1, "二维码不可用"))
              ]),
              (state.failed)
                ? (_openBlock$1(), _createElementBlock$1("p", _hoisted_7$1, _toDisplayString$1(state.failed), 1))
                : (_openBlock$1(), _createElementBlock$1("p", _hoisted_8$1, "用 " + _toDisplayString$1(activeClient.value.label) + " 扫描 · " + _toDisplayString$1(state.step), 1))
            ]),
            _: 1
          }),
          _createElementVNode$1("div", _hoisted_9$1, [
            _createVNode$1(_component_v_btn, {
              variant: "text",
              size: "small",
              "prepend-icon": "mdi-refresh",
              disabled: state.loading,
              onClick: issue
            }, {
              default: _withCtx$1(() => [...(_cache[4] || (_cache[4] = [
                _createTextVNode$1(" 换一张 ", -1)
              ]))]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode$1(_component_v_btn, {
              variant: "text",
              size: "small",
              onClick: _cache[1] || (_cache[1] = $event => (emit('update:modelValue', false)))
            }, {
              default: _withCtx$1(() => [...(_cache[5] || (_cache[5] = [
                _createTextVNode$1("关闭", -1)
              ]))]),
              _: 1
            })
          ])
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["model-value"]))
}
}

};
const QrLogin = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-fb3a5ece"]]);

const Config_vue_vue_type_style_index_0_scoped_f009881f_lang = '';

const {createVNode:_createVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,resolveComponent:_resolveComponent,withCtx:_withCtx,createBlock:_createBlock,unref:_unref} = await importShared('vue');


const _hoisted_1 = { class: "p115 cfg" };
const _hoisted_2 = { class: "cfg__shell" };
const _hoisted_3 = {
  class: "cfg__rail",
  "aria-label": "设置分区"
};
const _hoisted_4 = ["aria-current", "onClick"];
const _hoisted_5 = { class: "cfg__tab-text" };
const _hoisted_6 = { class: "cfg__tab-label" };
const _hoisted_7 = { class: "cfg__tab-note" };
const _hoisted_8 = { class: "cfg__pane" };
const _hoisted_9 = { key: 0 };
const _hoisted_10 = { class: "p115-panel" };
const _hoisted_11 = { class: "p115-panel__head" };
const _hoisted_12 = { class: "p115-panel__body" };
const _hoisted_13 = { class: "p115-panel" };
const _hoisted_14 = { class: "p115-panel__body" };
const _hoisted_15 = { class: "p115-fields" };
const _hoisted_16 = { class: "p115-switches mt-2" };
const _hoisted_17 = { key: 1 };
const _hoisted_18 = { class: "p115-panel" };
const _hoisted_19 = { class: "p115-panel__head" };
const _hoisted_20 = { class: "p115-panel__body" };
const _hoisted_21 = { class: "p115-switches" };
const _hoisted_22 = {
  key: 0,
  class: "p115-empty"
};
const _hoisted_23 = { key: 2 };
const _hoisted_24 = { class: "p115-panel" };
const _hoisted_25 = { class: "p115-panel__head" };
const _hoisted_26 = { class: "p115-panel__body" };
const _hoisted_27 = { class: "p115-switches" };
const _hoisted_28 = { class: "p115-fields mt-3" };
const _hoisted_29 = {
  key: 0,
  class: "p115-empty"
};
const _hoisted_30 = { key: 3 };
const _hoisted_31 = { class: "p115-panel" };
const _hoisted_32 = { class: "p115-panel__head" };
const _hoisted_33 = { class: "p115-panel__body" };
const _hoisted_34 = { class: "p115-fields" };
const _hoisted_35 = { class: "cfg__foot" };
const _hoisted_36 = { class: "cfg__foot-acts" };

const {computed,inject,onMounted,reactive,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: [Object, Function], default: null },
  saving: { type: Boolean, default: false },
},
  emits: ['save', 'close', 'switch', 'layout'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const config = reactive(normalizeConfig());
const section = ref('link');
const busy = ref(false);
const local = reactive({ text: '', kind: 'info' });
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text;
  local.kind = kind;
});

const qrOpen = ref(false);
const pick = reactive({ open: false, remote: false, title: '', apply: null });

const connected = computed(() => Boolean(String(config.cookie || '').trim()));
const redirectModes = [
  { title: 'Cookie 取链', value: 'cookie' },
  { title: 'Open API 取链', value: 'open' },
];
const sections = computed(() => [
  { key: 'link', icon: 'mdi-link-variant', label: '连接', note: connected.value ? '已授权' : '待授权' },
  { key: 'strm', icon: 'mdi-transit-connection-variant', label: 'STRM 通道', note: `${config.strm_mappings.length} 条` },
  { key: 'upload', icon: 'mdi-tray-arrow-up', label: '上传通道', note: `${config.upload_mappings.length} 条` },
  { key: 'checkin', icon: 'mdi-calendar-check-outline', label: '每日签到', note: config.checkin_enabled ? '已开启' : '已关闭' },
]);

function apply(value = {}) {
  Object.assign(config, normalizeConfig(value));
}

async function reload() {
  if (!props.api) return
  try {
    apply(await pluginGet(props.api, '/config'));
  } catch (error) {
    notice.error(error?.message || '配置读取失败');
  }
}

async function save() {
  if (!props.api) {
    emit('save', clone(config));
    return
  }
  busy.value = true;
  try {
    const result = await pluginPost(props.api, '/config', clone(config));
    if (result.success) {
      notice.success(result.message || '配置已保存');
      emit('save', clone(config));
    } else {
      notice.error(result.message || '保存失败');
    }
  } catch (error) {
    notice.error(error?.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

function useThisSite() {
  const origin = globalThis.location?.origin;
  if (!origin) return notice.error('无法识别当前站点地址')
  config.moviepilot_address = origin;
  notice.success('已填入当前站点地址');
}

function addStrm() {
  config.strm_mappings.push({ id: newId(), enabled: true, source_cid: '', source_path: '', target_dir: '' });
}

function addUpload() {
  config.upload_mappings.push({ id: newId(), enabled: true, source: '', target: '', strm_target: '' });
}

function drop(list, index) {
  list.splice(index, 1);
}

function openPicker(title, remote, apply_) {
  Object.assign(pick, { open: true, remote, title, apply: apply_ });
}

function onPicked(result) {
  pick.apply?.(result);
  pick.apply = null;
}

function strmStops(mapping) {
  return [
    { key: 'source', tag: '115 源目录', icon: 'mdi-cloud-outline', value: mapping.source_path, placeholder: '点击选择 115 目录' },
    { key: 'target', tag: 'STRM 输出', icon: 'mdi-folder-outline', value: mapping.target_dir, placeholder: '点击选择本地目录' },
  ]
}

function uploadStops(mapping) {
  const stops = [
    { key: 'source', tag: '本地源目录', icon: 'mdi-folder-outline', value: mapping.source, placeholder: '点击选择本地目录' },
    { key: 'target', tag: '115 目标目录', icon: 'mdi-cloud-outline', value: mapping.target, placeholder: '点击选择 115 目录' },
  ];
  if (config.upload_generate_strm) {
    stops.push({ key: 'strm', tag: 'STRM 输出', icon: 'mdi-file-link-outline', value: mapping.strm_target, placeholder: '点击选择本地目录' });
  }
  return stops
}

function pickStrm(mapping, key) {
  if (key === 'source') {
    openPicker('选择 115 源目录', true, result => {
      mapping.source_cid = result.cid;
      mapping.source_path = result.path;
    });
  } else {
    openPicker('选择 STRM 输出目录', false, result => {
      mapping.target_dir = result.path;
    });
  }
}

function pickUpload(mapping, key) {
  if (key === 'source') {
    openPicker('选择本地源目录', false, result => {
      mapping.source = result.path;
    });
  } else if (key === 'target') {
    openPicker('选择 115 目标目录', true, result => {
      mapping.target = result.path;
    });
  } else {
    openPicker('选择 STRM 输出目录', false, result => {
      mapping.strm_target = result.path;
    });
  }
}

watch(() => props.initialConfig, apply, { immediate: true, deep: true });
onMounted(() => emit('layout', { maxWidth: '58rem' }));

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_textarea = _resolveComponent("v-textarea");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(AppBar, {
      view: "设置",
      online: connected.value,
      busy: busy.value,
      "show-refresh": "",
      onRefresh: reload,
      onSwitch: _cache[0] || (_cache[0] = $event => (emit('switch'))),
      onClose: _cache[1] || (_cache[1] = $event => (emit('close')))
    }, null, 8, ["online", "busy"]),
    (local.text)
      ? (_openBlock(), _createElementBlock("button", {
          key: 0,
          type: "button",
          class: _normalizeClass(["cfg__local", `cfg__local--${local.kind}`]),
          onClick: _cache[2] || (_cache[2] = $event => (local.text = ''))
        }, [
          _createTextVNode(_toDisplayString(local.text) + " ", 1),
          _cache[29] || (_cache[29] = _createElementVNode("span", { class: "cfg__local-dismiss" }, "知道了", -1))
        ], 2))
      : _createCommentVNode("", true),
    _createElementVNode("div", _hoisted_2, [
      _createElementVNode("nav", _hoisted_3, [
        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(sections.value, (item) => {
          return (_openBlock(), _createElementBlock("button", {
            key: item.key,
            type: "button",
            class: _normalizeClass(["cfg__tab", { 'cfg__tab--on': section.value === item.key }]),
            "aria-current": section.value === item.key ? 'true' : undefined,
            onClick: $event => (section.value = item.key)
          }, [
            _createVNode(_component_v_icon, {
              icon: item.icon,
              size: "17"
            }, null, 8, ["icon"]),
            _createElementVNode("span", _hoisted_5, [
              _createElementVNode("span", _hoisted_6, _toDisplayString(item.label), 1),
              _createElementVNode("span", _hoisted_7, _toDisplayString(item.note), 1)
            ])
          ], 10, _hoisted_4))
        }), 128))
      ]),
      _createElementVNode("div", _hoisted_8, [
        (section.value === 'link')
          ? (_openBlock(), _createElementBlock("section", _hoisted_9, [
              _createElementVNode("div", _hoisted_10, [
                _createElementVNode("div", _hoisted_11, [
                  _cache[31] || (_cache[31] = _createElementVNode("div", null, [
                    _createElementVNode("h3", { class: "p115-section-title" }, "115 授权"),
                    _createElementVNode("p", { class: "p115-hint" }, "扫码后 Cookie 由后端写入，也可以手动粘贴已有的 Cookie。")
                  ], -1)),
                  _createVNode(_component_v_btn, {
                    color: "primary",
                    variant: "flat",
                    size: "small",
                    "prepend-icon": "mdi-qrcode-scan",
                    onClick: _cache[3] || (_cache[3] = $event => (qrOpen.value = true))
                  }, {
                    default: _withCtx(() => [...(_cache[30] || (_cache[30] = [
                      _createTextVNode(" 扫码登录 ", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                _createElementVNode("div", _hoisted_12, [
                  _createVNode(_component_v_text_field, {
                    modelValue: config.cookie,
                    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.cookie) = $event)),
                    label: "115 Cookie",
                    type: "password",
                    variant: "outlined",
                    density: "compact",
                    "hide-details": "",
                    autocomplete: "off",
                    placeholder: "UID=...; CID=...; SEID=..."
                  }, null, 8, ["modelValue"]),
                  _cache[32] || (_cache[32] = _createElementVNode("p", { class: "p115-hint" }, "Cookie 只保存在 MoviePilot 本地配置里，界面不会回显明文。", -1))
                ])
              ]),
              _createElementVNode("div", _hoisted_13, [
                _cache[34] || (_cache[34] = _createElementVNode("div", { class: "p115-panel__head" }, [
                  _createElementVNode("div", null, [
                    _createElementVNode("h3", { class: "p115-section-title" }, "播放地址"),
                    _createElementVNode("p", { class: "p115-hint" }, "STRM 里写入的回源地址，播放器要能访问到它。")
                  ])
                ], -1)),
                _createElementVNode("div", _hoisted_14, [
                  _createElementVNode("div", _hoisted_15, [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.moviepilot_address,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.moviepilot_address) = $event)),
                      label: "MoviePilot 访问地址",
                      variant: "outlined",
                      density: "compact",
                      "hide-details": "",
                      placeholder: "http://HOST:PORT"
                    }, {
                      "append-inner": _withCtx(() => [
                        _createVNode(_component_v_btn, {
                          variant: "text",
                          size: "x-small",
                          onClick: useThisSite
                        }, {
                          default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
                            _createTextVNode("用当前站点", -1)
                          ]))]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }, 8, ["modelValue"]),
                    _createVNode(_component_v_select, {
                      modelValue: config.link_redirect_mode,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.link_redirect_mode) = $event)),
                      items: redirectModes,
                      label: "取链方式",
                      variant: "outlined",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _createElementVNode("div", _hoisted_16, [
                    _createVNode(_component_v_switch, {
                      modelValue: config.enabled,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.enabled) = $event)),
                      color: "primary",
                      density: "compact",
                      "hide-details": "",
                      label: "启用插件"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_switch, {
                      modelValue: config.same_playback,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.same_playback) = $event)),
                      color: "primary",
                      density: "compact",
                      "hide-details": "",
                      label: "播放时同步 115 观看记录"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_switch, {
                      modelValue: config.life_monitor_enabled,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.life_monitor_enabled) = $event)),
                      color: "primary",
                      density: "compact",
                      "hide-details": "",
                      label: "监听 115 生活事件，自动增量同步"
                    }, null, 8, ["modelValue"])
                  ])
                ])
              ])
            ]))
          : (section.value === 'strm')
            ? (_openBlock(), _createElementBlock("section", _hoisted_17, [
                _createElementVNode("div", _hoisted_18, [
                  _createElementVNode("div", _hoisted_19, [
                    _cache[36] || (_cache[36] = _createElementVNode("div", null, [
                      _createElementVNode("h3", { class: "p115-section-title" }, "STRM 通道"),
                      _createElementVNode("p", { class: "p115-hint" }, "每条通道把一个 115 目录的媒体文件生成为本地 STRM。")
                    ], -1)),
                    _createVNode(_component_v_btn, {
                      variant: "outlined",
                      size: "small",
                      "prepend-icon": "mdi-plus",
                      onClick: addStrm
                    }, {
                      default: _withCtx(() => [...(_cache[35] || (_cache[35] = [
                        _createTextVNode("加一条通道", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _createElementVNode("div", _hoisted_20, [
                    _createElementVNode("div", _hoisted_21, [
                      _createVNode(_component_v_switch, {
                        modelValue: config.strm_incremental,
                        "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.strm_incremental) = $event)),
                        color: "primary",
                        density: "compact",
                        "hide-details": "",
                        label: "只处理新增和变化的文件"
                      }, null, 8, ["modelValue"]),
                      _createVNode(_component_v_switch, {
                        modelValue: config.strm_download_sidecars,
                        "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.strm_download_sidecars) = $event)),
                        color: "primary",
                        density: "compact",
                        "hide-details": "",
                        label: "一并下载刮削文件和字幕"
                      }, null, 8, ["modelValue"]),
                      _createVNode(_component_v_switch, {
                        modelValue: config.strm_delete_cloud_on_missing,
                        "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.strm_delete_cloud_on_missing) = $event)),
                        color: "primary",
                        density: "compact",
                        "hide-details": "",
                        label: "本地 STRM 被删除时同步删除 115 对应文件"
                      }, null, 8, ["modelValue"])
                    ]),
                    _createVNode(NotifyRow, {
                      enabled: config.strm_notify,
                      "onUpdate:enabled": _cache[13] || (_cache[13] = $event => ((config.strm_notify) = $event)),
                      type: config.strm_notify_type,
                      "onUpdate:type": _cache[14] || (_cache[14] = $event => ((config.strm_notify_type) = $event)),
                      types: config.notify_types,
                      label: "STRM 同步完成后发送通知",
                      hint: "每次同步结束发一条，逐条列出映射的新增、更新与失败数。"
                    }, null, 8, ["enabled", "type", "types"])
                  ])
                ]),
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(config.strm_mappings, (mapping, index) => {
                  return (_openBlock(), _createBlock(Conduit, {
                    key: mapping.id,
                    enabled: mapping.enabled !== false,
                    stops: strmStops(mapping),
                    index: index,
                    "onUpdate:enabled": value => (mapping.enabled = value),
                    onPick: key => pickStrm(mapping, key),
                    onRemove: $event => (drop(config.strm_mappings, index))
                  }, null, 8, ["enabled", "stops", "index", "onUpdate:enabled", "onPick", "onRemove"]))
                }), 128)),
                (!config.strm_mappings.length)
                  ? (_openBlock(), _createElementBlock("p", _hoisted_22, " 还没有 STRM 通道。加一条，选好 115 源目录和本地输出目录就能同步。 "))
                  : _createCommentVNode("", true)
              ]))
            : (section.value === 'upload')
              ? (_openBlock(), _createElementBlock("section", _hoisted_23, [
                  _createElementVNode("div", _hoisted_24, [
                    _createElementVNode("div", _hoisted_25, [
                      _cache[38] || (_cache[38] = _createElementVNode("div", null, [
                        _createElementVNode("h3", { class: "p115-section-title" }, "上传通道"),
                        _createElementVNode("p", { class: "p115-hint" }, "每条通道把一个本地目录的媒体文件上传到 115。")
                      ], -1)),
                      _createVNode(_component_v_btn, {
                        variant: "outlined",
                        size: "small",
                        "prepend-icon": "mdi-plus",
                        onClick: addUpload
                      }, {
                        default: _withCtx(() => [...(_cache[37] || (_cache[37] = [
                          _createTextVNode("加一条通道", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _createElementVNode("div", _hoisted_26, [
                      _createElementVNode("div", _hoisted_27, [
                        _createVNode(_component_v_switch, {
                          modelValue: config.upload_include_sidecars,
                          "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.upload_include_sidecars) = $event)),
                          color: "primary",
                          density: "compact",
                          "hide-details": "",
                          label: "一并上传刮削文件和字幕"
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_v_switch, {
                          modelValue: config.upload_generate_strm,
                          "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((config.upload_generate_strm) = $event)),
                          color: "primary",
                          density: "compact",
                          "hide-details": "",
                          label: "上传后生成 STRM"
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_v_switch, {
                          modelValue: config.upload_delete_source,
                          "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((config.upload_delete_source) = $event)),
                          color: "primary",
                          density: "compact",
                          "hide-details": "",
                          label: "上传成功后删除本地源文件"
                        }, null, 8, ["modelValue"])
                      ]),
                      _createElementVNode("div", _hoisted_28, [
                        _createVNode(_component_v_textarea, {
                          modelValue: config.upload_media_extensions,
                          "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((config.upload_media_extensions) = $event)),
                          label: "媒体文件后缀",
                          variant: "outlined",
                          density: "compact",
                          rows: "2",
                          "auto-grow": "",
                          "hide-details": ""
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_v_textarea, {
                          modelValue: config.upload_sidecar_extensions,
                          "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((config.upload_sidecar_extensions) = $event)),
                          label: "刮削文件后缀",
                          variant: "outlined",
                          density: "compact",
                          rows: "2",
                          "auto-grow": "",
                          "hide-details": ""
                        }, null, 8, ["modelValue"])
                      ]),
                      _cache[39] || (_cache[39] = _createElementVNode("p", { class: "p115-hint" }, [
                        _createTextVNode("用英文逗号分隔，带上点号，例如 "),
                        _createElementVNode("span", { class: "p115-mono" }, ".mp4,.mkv"),
                        _createTextVNode("。")
                      ], -1)),
                      _createVNode(NotifyRow, {
                        enabled: config.upload_notify,
                        "onUpdate:enabled": _cache[20] || (_cache[20] = $event => ((config.upload_notify) = $event)),
                        type: config.upload_notify_type,
                        "onUpdate:type": _cache[21] || (_cache[21] = $event => ((config.upload_notify_type) = $event)),
                        types: config.notify_types,
                        label: "上传完成后发送通知",
                        hint: "汇报上传、秒传、生成 STRM 与失败数，手动触发和整理入库后的自动上传都算。通知海报自动使用 MoviePilot 内置的 TMDB 配置。"
                      }, null, 8, ["enabled", "type", "types"])
                    ])
                  ]),
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(config.upload_mappings, (mapping, index) => {
                    return (_openBlock(), _createBlock(Conduit, {
                      key: mapping.id,
                      enabled: mapping.enabled !== false,
                      stops: uploadStops(mapping),
                      index: index,
                      "onUpdate:enabled": value => (mapping.enabled = value),
                      onPick: key => pickUpload(mapping, key),
                      onRemove: $event => (drop(config.upload_mappings, index))
                    }, null, 8, ["enabled", "stops", "index", "onUpdate:enabled", "onPick", "onRemove"]))
                  }), 128)),
                  (!config.upload_mappings.length)
                    ? (_openBlock(), _createElementBlock("p", _hoisted_29, " 还没有上传通道。加一条，选好本地源目录和 115 目标目录就能上传。 "))
                    : _createCommentVNode("", true)
                ]))
              : (_openBlock(), _createElementBlock("section", _hoisted_30, [
                  _createElementVNode("div", _hoisted_31, [
                    _createElementVNode("div", _hoisted_32, [
                      _cache[40] || (_cache[40] = _createElementVNode("div", null, [
                        _createElementVNode("h3", { class: "p115-section-title" }, "每日签到"),
                        _createElementVNode("p", { class: "p115-hint" }, "按 cron 触发，在时间窗内随机挑一刻执行，看起来更像人在操作。")
                      ], -1)),
                      _createVNode(_component_v_switch, {
                        modelValue: config.checkin_enabled,
                        "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((config.checkin_enabled) = $event)),
                        color: "primary",
                        density: "compact",
                        "hide-details": "",
                        label: config.checkin_enabled ? '已开启' : '已关闭'
                      }, null, 8, ["modelValue", "label"])
                    ]),
                    _createElementVNode("div", _hoisted_33, [
                      _createElementVNode("div", _hoisted_34, [
                        _createVNode(_component_v_text_field, {
                          modelValue: config.checkin_cron,
                          "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((config.checkin_cron) = $event)),
                          label: "cron 表达式",
                          variant: "outlined",
                          density: "compact",
                          "hide-details": "",
                          placeholder: "15 8 * * *"
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_v_text_field, {
                          modelValue: config.checkin_time_range,
                          "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((config.checkin_time_range) = $event)),
                          label: "随机时间窗",
                          variant: "outlined",
                          density: "compact",
                          "hide-details": "",
                          placeholder: "06:00-09:00"
                        }, null, 8, ["modelValue"])
                      ]),
                      _cache[41] || (_cache[41] = _createElementVNode("p", { class: "p115-hint" }, "时间窗留空就在 cron 命中的那一刻直接签到。", -1)),
                      _createVNode(NotifyRow, {
                        enabled: config.checkin_notify,
                        "onUpdate:enabled": _cache[25] || (_cache[25] = $event => ((config.checkin_notify) = $event)),
                        type: config.checkin_notify_type,
                        "onUpdate:type": _cache[26] || (_cache[26] = $event => ((config.checkin_notify_type) = $event)),
                        types: config.notify_types,
                        label: "签到后发送通知",
                        hint: "成功带上连续天数和本次积分，失败带上原因。"
                      }, null, 8, ["enabled", "type", "types"])
                    ])
                  ])
                ]))
      ])
    ]),
    _createElementVNode("footer", _hoisted_35, [
      _cache[44] || (_cache[44] = _createElementVNode("span", { class: "cfg__foot-note p115-muted" }, "保存后立即生效，无需重启 MoviePilot。", -1)),
      _createElementVNode("div", _hoisted_36, [
        _createVNode(_component_v_btn, {
          variant: "text",
          size: "small",
          disabled: busy.value,
          onClick: reload
        }, {
          default: _withCtx(() => [...(_cache[42] || (_cache[42] = [
            _createTextVNode("放弃改动", -1)
          ]))]),
          _: 1
        }, 8, ["disabled"]),
        _createVNode(_component_v_btn, {
          color: "primary",
          variant: "flat",
          size: "small",
          loading: busy.value || __props.saving,
          onClick: save
        }, {
          default: _withCtx(() => [...(_cache[43] || (_cache[43] = [
            _createTextVNode("保存配置", -1)
          ]))]),
          _: 1
        }, 8, ["loading"])
      ])
    ]),
    _createVNode(QrLogin, {
      modelValue: qrOpen.value,
      "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((qrOpen).value = $event)),
      api: __props.api,
      onAuthenticated: reload,
      onError: _unref(notice).error
    }, null, 8, ["modelValue", "api", "onError"]),
    _createVNode(DirPicker, {
      modelValue: pick.open,
      "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((pick.open) = $event)),
      api: __props.api,
      remote: pick.remote,
      title: pick.title,
      onSelect: onPicked,
      onError: _unref(notice).error
    }, null, 8, ["modelValue", "api", "remote", "title", "onError"])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-f009881f"]]);

export { Config as default };
