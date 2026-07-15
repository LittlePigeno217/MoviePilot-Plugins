import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, n as normalizeConfig, c as clone, a as pluginPost, p as pluginGet } from './_plugin-vue_export-helper-acbf976c.js';

const Config_vue_vue_type_style_index_0_scoped_c3e0c4a1_lang = '';

const Config_vue_vue_type_style_index_1_scoped_c3e0c4a1_lang = '';

const {createElementVNode:_createElementVNode,normalizeClass:_normalizeClass,resolveComponent:_resolveComponent,mergeProps:_mergeProps,createVNode:_createVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,withModifiers:_withModifiers,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "station-config" };
const _hoisted_2 = { class: "station-head" };
const _hoisted_3 = {
  class: "signal-rail",
  "aria-label": "处理链路"
};
const _hoisted_4 = { class: "head-tools" };
const _hoisted_5 = { class: "station-shell" };
const _hoisted_6 = {
  class: "station-nav",
  "aria-label": "配置区域"
};
const _hoisted_7 = { class: "station-workspace" };
const _hoisted_8 = { class: "work-header" };
const _hoisted_9 = { class: "auth-deck" };
const _hoisted_10 = { class: "auth-portal" };
const _hoisted_11 = { class: "auth-portal-head" };
const _hoisted_12 = { class: "cookie-vault" };
const _hoisted_13 = { class: "auth-state-icon" };
const _hoisted_14 = { class: "work-header" };
const _hoisted_15 = { class: "strm-address-row" };
const _hoisted_16 = { class: "mapping-list" };
const _hoisted_17 = {
  key: 0,
  class: "empty-row"
};
const _hoisted_18 = { class: "work-header" };
const _hoisted_19 = { class: "head-switches" };
const _hoisted_20 = { class: "work-grid extension-grid" };
const _hoisted_21 = { class: "mapping-list" };
const _hoisted_22 = {
  key: 0,
  class: "empty-row"
};
const _hoisted_23 = { class: "work-header" };
const _hoisted_24 = { class: "work-grid checkin-grid" };
const _hoisted_25 = { class: "station-footer" };
const _hoisted_26 = { class: "save-state" };
const _hoisted_27 = { class: "qr-login-head" };
const _hoisted_28 = {
  key: 1,
  class: "qr-loading"
};
const _hoisted_29 = { class: "qr-client-types" };
const _hoisted_30 = {
  key: 0,
  class: "qr-code-stage"
};
const _hoisted_31 = { class: "qr-code-frame" };
const _hoisted_32 = ["src"];
const _hoisted_33 = { class: "picker-head" };
const _hoisted_34 = { class: "picker-toolbar" };
const _hoisted_35 = { class: "mono" };

const {computed,onBeforeUnmount,reactive,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: null },
  saving: { type: Boolean, default: false },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const config = reactive(normalizeConfig());
const activeTab = ref('login');
const notice = ref('');
const noticeColor = ref('info');
const qrClients = [
  { label: '支付宝', value: 'alipaymini' },
  { label: '微信', value: 'wechatmini' },
  { label: '安卓', value: '115android' },
  { label: 'iOS', value: '115ios' },
  { label: '网页', value: 'web' },
  { label: 'PAD', value: '115ipad' },
  { label: 'TV', value: 'tv' },
];
const qrDialog = reactive({ open: false, loading: false, error: '', code: '', clientType: 'alipaymini', status: '等待扫码', timer: null });
const picker = reactive({ open: false, type: '', index: -1, cid: '0', path: '', localBase: '', roots: [], remoteTrail: [], items: [] });
const pickerTitle = computed(() => ({ strm_source: '选择 115 源目录', upload_target: '选择 115 上传目录', strm_target: '选择本地 STRM 目录', upload_source: '选择本地上传目录' }[picker.type] || '选择目录'));
const isRemotePicker = computed(() => ['strm_source', 'upload_target'].includes(picker.type));
const connectionReady = computed(() => Boolean(String(config.cookie || '').trim()));
const selectedQrClient = computed(() => qrClients.find(item => item.value === qrDialog.clientType) || qrClients[0]);

function applyConfig(value = {}) {
  Object.assign(config, normalizeConfig(value));
}

function tell(text, color = 'info') {
  notice.value = text;
  noticeColor.value = color;
}

async function save() {
  if (!props.api) {
    emit('save', clone(config));
    return
  }
  try {
    const result = await pluginPost(props.api, '/config', clone(config));
    tell(result.message || '配置已保存', result.success ? 'success' : 'error');
    if (result.success) emit('save', clone(config));
  } catch (error) {
    tell(error?.message || '保存失败', 'error');
  }
}

function addStrmMapping() {
  config.strm_mappings.push({ id: crypto.randomUUID?.() || String(Date.now()), enabled: true, source_cid: '', source_path: '', target_dir: '' });
}

function useCurrentMoviePilotAddress() {
  const origin = globalThis.location?.origin;
  if (!origin) return tell('无法识别当前站点地址', 'error')
  config.moviepilot_address = origin;
  tell('已使用当前站点地址', 'success');
}

function addUploadMapping() {
  config.upload_mappings.push({ enabled: true, source: '', target: '' });
}

function remove(items, index) {
  items.splice(index, 1);
}

function clearQrPoll() {
  if (qrDialog.timer) {
    clearInterval(qrDialog.timer);
    qrDialog.timer = null;
  }
}

async function pollQrLogin() {
  try {
    const data = await pluginGet(props.api, '/check-login');
    const status = Number(data.status);
    if (status === 2) {
      clearQrPoll();
      qrDialog.status = '登录成功';
      applyConfig(await pluginGet(props.api, '/config'));
      tell('115 登录成功，Cookie 已保存', 'success');
    } else if (status === 1) {
      qrDialog.status = '已扫码，请在设备上确认';
    } else if (status === -1 || status === -2) {
      clearQrPoll();
      qrDialog.status = status === -1 ? '二维码已过期' : '已取消登录';
      qrDialog.error = data.tip || qrDialog.status;
    } else {
      qrDialog.status = data.tip || '等待扫码';
    }
  } catch (error) {
    clearQrPoll();
    qrDialog.error = error?.message || '登录状态检查失败';
  }
}

async function refreshQrCode() {
  clearQrPoll();
  qrDialog.loading = true;
  qrDialog.error = '';
  qrDialog.code = '';
  qrDialog.status = '正在获取二维码';
  try {
    const result = await pluginPost(props.api, '/qrcode', { client_type: qrDialog.clientType });
    if (!result.success || !result.data?.qrcode) throw new Error(result.message || '115 未返回二维码')
    qrDialog.code = result.data.qrcode;
    qrDialog.clientType = result.data.client_type || qrDialog.clientType;
    qrDialog.status = '等待扫码';
    qrDialog.timer = window.setInterval(pollQrLogin, 3000);
  } catch (error) {
    qrDialog.error = error?.message || '获取二维码失败';
  } finally {
    qrDialog.loading = false;
  }
}

async function openQrDialog() {
  qrDialog.open = true;
  await refreshQrCode();
}

function closeQrDialog() {
  clearQrPoll();
  qrDialog.open = false;
}

async function selectQrClient(clientType) {
  if (clientType === qrDialog.clientType) return
  qrDialog.clientType = clientType;
  await refreshQrCode();
}

async function openPicker(type, index) {
  Object.assign(picker, { open: true, type, index, cid: '0', path: '', localBase: '', roots: [], remoteTrail: [], items: [] });
  await browsePicker();
}

async function browsePicker(next) {
  try {
    if (isRemotePicker.value) {
      if (next) {
        picker.remoteTrail.push({ cid: picker.cid, name: next.name });
        picker.cid = next.cid;
      }
      const data = await pluginGet(props.api, '/browse-115', { cid: picker.cid });
      picker.items = data.items || [];
    } else {
      if (next) picker.path = next.path;
      const data = await pluginGet(props.api, '/browse-local', { path: picker.path, root: picker.localBase });
      picker.localBase = data.base || picker.localBase;
      picker.roots = data.roots || picker.roots;
      picker.path = data.current || '';
      picker.items = data.items || [];
    }
  } catch (error) {
    tell(error?.message || '目录读取失败', 'error');
  }
}

async function switchLocalRoot(root) {
  picker.localBase = root || '';
  picker.path = '';
  await browsePicker();
}

async function pickerBack() {
  if (isRemotePicker.value) {
    const previous = picker.remoteTrail.pop();
    if (!previous) return
    picker.cid = previous.cid;
  } else if (picker.path) {
    picker.path = picker.path.split('/').slice(0, -1).join('/');
  } else {
    return
  }
  await browsePicker();
}

function selectPicker() {
  const localPath = picker.path ? `${picker.localBase.replace(/[\\/]+$/, '')}/${picker.path}` : picker.localBase;
  if (picker.type === 'strm_source') {
    const mapping = config.strm_mappings[picker.index];
    mapping.source_cid = picker.cid;
    mapping.source_path = `/${picker.remoteTrail.map(item => item.name).join('/')}`.replace(/\/$/, '') || '/';
  } else if (picker.type === 'upload_target') {
    config.upload_mappings[picker.index].target = `/${picker.remoteTrail.map(item => item.name).join('/')}`.replace(/\/$/, '') || '/';
  } else if (picker.type === 'strm_target') {
    config.strm_mappings[picker.index].target_dir = localPath;
  } else if (picker.type === 'upload_source') {
    config.upload_mappings[picker.index].source = localPath;
  }
  picker.open = false;
}

watch(() => props.initialConfig, applyConfig, { immediate: true, deep: true });
onBeforeUnmount(clearQrPoll);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_tooltip = _resolveComponent("v-tooltip");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_window_item = _resolveComponent("v-window-item");
  const _component_v_window = _resolveComponent("v-window");
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_dialog = _resolveComponent("v-dialog");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_list = _resolveComponent("v-list");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("header", _hoisted_2, [
      _cache[28] || (_cache[28] = _createElementVNode("div", { class: "station-title" }, [
        _createElementVNode("span", { class: "kicker" }, "115 DRIVE / CONTROL ROOM"),
        _createElementVNode("div", { class: "title-row" }, [
          _createElementVNode("span", { class: "title-index" }, "115"),
          _createElementVNode("h2", null, "轻量助手")
        ])
      ], -1)),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("span", {
          class: _normalizeClass({ active: connectionReady.value })
        }, [...(_cache[23] || (_cache[23] = [
          _createElementVNode("i", null, "115", -1),
          _createElementVNode("b", null, "授权", -1)
        ]))], 2),
        _cache[26] || (_cache[26] = _createElementVNode("em", null, null, -1)),
        _createElementVNode("span", {
          class: _normalizeClass({ active: config.enabled })
        }, [...(_cache[24] || (_cache[24] = [
          _createElementVNode("i", null, "302", -1),
          _createElementVNode("b", null, "转发", -1)
        ]))], 2),
        _cache[27] || (_cache[27] = _createElementVNode("em", null, null, -1)),
        _createElementVNode("span", {
          class: _normalizeClass({ active: config.strm_mappings.length })
        }, [...(_cache[25] || (_cache[25] = [
          _createElementVNode("i", null, "STRM", -1),
          _createElementVNode("b", null, "落盘", -1)
        ]))], 2)
      ]),
      _createElementVNode("div", _hoisted_4, [
        _createVNode(_component_v_tooltip, {
          text: "运行台",
          location: "bottom"
        }, {
          activator: _withCtx(({ props: tipProps }) => [
            _createVNode(_component_v_btn, _mergeProps(tipProps, {
              icon: "mdi-view-dashboard-outline",
              variant: "text",
              size: "small",
              onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
            }), null, 16)
          ]),
          _: 1
        }),
        _createVNode(_component_v_tooltip, {
          text: "关闭",
          location: "bottom"
        }, {
          activator: _withCtx(({ props: tipProps }) => [
            _createVNode(_component_v_btn, _mergeProps(tipProps, {
              icon: "mdi-close",
              variant: "text",
              size: "small",
              onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
            }), null, 16)
          ]),
          _: 1
        })
      ])
    ]),
    _createElementVNode("div", _hoisted_5, [
      _createElementVNode("nav", _hoisted_6, [
        _createElementVNode("button", {
          class: _normalizeClass({ current: activeTab.value === 'login' }),
          onClick: _cache[2] || (_cache[2] = $event => (activeTab.value = 'login'))
        }, [
          _createVNode(_component_v_icon, {
            icon: "mdi-shield-key-outline",
            size: "18"
          }),
          _cache[29] || (_cache[29] = _createElementVNode("span", null, "登录", -1))
        ], 2),
        _createElementVNode("button", {
          class: _normalizeClass({ current: activeTab.value === 'strm' }),
          onClick: _cache[3] || (_cache[3] = $event => (activeTab.value = 'strm'))
        }, [
          _createVNode(_component_v_icon, {
            icon: "mdi-file-link-outline",
            size: "18"
          }),
          _cache[30] || (_cache[30] = _createElementVNode("span", null, "STRM", -1)),
          _createElementVNode("b", null, _toDisplayString(config.strm_mappings.length), 1)
        ], 2),
        _createElementVNode("button", {
          class: _normalizeClass({ current: activeTab.value === 'upload' }),
          onClick: _cache[4] || (_cache[4] = $event => (activeTab.value = 'upload'))
        }, [
          _createVNode(_component_v_icon, {
            icon: "mdi-folder-upload-outline",
            size: "18"
          }),
          _cache[31] || (_cache[31] = _createElementVNode("span", null, "目录上传", -1)),
          _createElementVNode("b", null, _toDisplayString(config.upload_mappings.length), 1)
        ], 2),
        _createElementVNode("button", {
          class: _normalizeClass({ current: activeTab.value === 'checkin' }),
          onClick: _cache[5] || (_cache[5] = $event => (activeTab.value = 'checkin'))
        }, [
          _createVNode(_component_v_icon, {
            icon: "mdi-calendar-check-outline",
            size: "18"
          }),
          _cache[32] || (_cache[32] = _createElementVNode("span", null, "签到", -1))
        ], 2)
      ]),
      _createElementVNode("main", _hoisted_7, [
        (notice.value)
          ? (_openBlock(), _createBlock(_component_v_alert, {
              key: 0,
              type: noticeColor.value,
              density: "compact",
              variant: "tonal",
              class: "station-alert"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(notice.value), 1)
              ]),
              _: 1
            }, 8, ["type"]))
          : _createCommentVNode("", true),
        _createVNode(_component_v_window, {
          modelValue: activeTab.value,
          "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((activeTab).value = $event)),
          touch: false
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_window_item, { value: "login" }, {
              default: _withCtx(() => [
                _createElementVNode("section", _hoisted_8, [
                  _cache[33] || (_cache[33] = _createElementVNode("div", null, [
                    _createElementVNode("span", { class: "work-code" }, "AUTH / 115"),
                    _createElementVNode("h3", null, "授权连接")
                  ], -1)),
                  _createVNode(_component_v_switch, {
                    modelValue: config.enabled,
                    "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.enabled) = $event)),
                    label: "启用插件",
                    color: "primary",
                    "hide-details": "",
                    density: "compact",
                    class: "head-switch"
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode("section", _hoisted_9, [
                  _createElementVNode("div", _hoisted_10, [
                    _createElementVNode("div", _hoisted_11, [
                      _cache[35] || (_cache[35] = _createElementVNode("div", null, [
                        _createElementVNode("span", { class: "work-code" }, "QR / SECURE SESSION"),
                        _createElementVNode("h4", null, "扫码授权")
                      ], -1)),
                      _createElementVNode("span", {
                        class: _normalizeClass(["auth-chip", { ready: connectionReady.value }])
                      }, [
                        _cache[34] || (_cache[34] = _createElementVNode("i", null, null, -1)),
                        _createTextVNode(_toDisplayString(connectionReady.value ? '已保存' : '未授权'), 1)
                      ], 2)
                    ]),
                    _createVNode(_component_v_btn, {
                      class: "auth-qr-action station-primary",
                      size: "large",
                      block: "",
                      "prepend-icon": "mdi-qrcode-scan",
                      onClick: openQrDialog
                    }, {
                      default: _withCtx(() => [...(_cache[36] || (_cache[36] = [
                        _createTextVNode("扫码登录 115", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _createElementVNode("div", _hoisted_12, [
                    _cache[37] || (_cache[37] = _createElementVNode("div", { class: "cookie-vault-head" }, [
                      _createElementVNode("span", { class: "work-code" }, "COOKIE / CREDENTIAL"),
                      _createElementVNode("span", null, "手工凭据")
                    ], -1)),
                    _createVNode(_component_v_text_field, {
                      modelValue: config.cookie,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.cookie) = $event)),
                      type: "password",
                      label: "115 Cookie",
                      variant: "outlined",
                      density: "comfortable",
                      "hide-details": "",
                      autocomplete: "new-password",
                      spellcheck: "false",
                      class: "cookie-field"
                    }, null, 8, ["modelValue"])
                  ]),
                  _createElementVNode("aside", {
                    class: _normalizeClass(["auth-state", { ready: connectionReady.value }])
                  }, [
                    _createElementVNode("span", _hoisted_13, [
                      _createVNode(_component_v_icon, {
                        icon: connectionReady.value ? 'mdi-shield-check-outline' : 'mdi-shield-key-outline',
                        size: "26"
                      }, null, 8, ["icon"])
                    ]),
                    _cache[38] || (_cache[38] = _createElementVNode("span", { class: "work-code" }, "115 SESSION", -1)),
                    _createElementVNode("strong", null, _toDisplayString(connectionReady.value ? '凭据已保存' : '等待授权'), 1)
                  ], 2)
                ])
              ]),
              _: 1
            }),
            _createVNode(_component_v_window_item, { value: "strm" }, {
              default: _withCtx(() => [
                _createElementVNode("section", _hoisted_14, [
                  _cache[39] || (_cache[39] = _createElementVNode("div", null, [
                    _createElementVNode("span", { class: "work-code" }, "ROUTE / STRM"),
                    _createElementVNode("h3", null, "文件映射")
                  ], -1)),
                  _createVNode(_component_v_switch, {
                    modelValue: config.strm_incremental,
                    "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.strm_incremental) = $event)),
                    label: "增量生成",
                    color: "primary",
                    "hide-details": "",
                    density: "compact",
                    class: "head-switch"
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode("section", _hoisted_15, [
                  _createVNode(_component_v_text_field, {
                    modelValue: config.moviepilot_address,
                    "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.moviepilot_address) = $event)),
                    label: "STRM 文件内链接地址",
                    placeholder: "http://moviepilot:3000",
                    variant: "outlined",
                    density: "comfortable",
                    "hide-details": ""
                  }, {
                    "append-inner": _withCtx(() => [
                      _createVNode(_component_v_tooltip, {
                        text: "使用当前站点地址",
                        location: "top"
                      }, {
                        activator: _withCtx(({ props: tipProps }) => [
                          _createVNode(_component_v_btn, _mergeProps(tipProps, {
                            "aria-label": "使用当前站点地址",
                            icon: "mdi-web",
                            variant: "text",
                            size: "small",
                            onClick: _withModifiers(useCurrentMoviePilotAddress, ["stop"])
                          }), null, 16)
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["modelValue"])
                ]),
                _createElementVNode("div", _hoisted_16, [
                  _cache[41] || (_cache[41] = _createElementVNode("div", { class: "mapping-caption" }, [
                    _createElementVNode("span", null, "115 源目录"),
                    _createElementVNode("span", null, "本地 STRM 输出目录")
                  ], -1)),
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(config.strm_mappings, (mapping, index) => {
                    return (_openBlock(), _createElementBlock("section", {
                      key: mapping.id || index,
                      class: "mapping-row"
                    }, [
                      _createVNode(_component_v_switch, {
                        modelValue: mapping.enabled,
                        "onUpdate:modelValue": $event => ((mapping.enabled) = $event),
                        "aria-label": "启用映射",
                        color: "primary",
                        "hide-details": "",
                        density: "compact"
                      }, null, 8, ["modelValue", "onUpdate:modelValue"]),
                      _createVNode(_component_v_text_field, {
                        modelValue: mapping.source_path,
                        "onUpdate:modelValue": $event => ((mapping.source_path) = $event),
                        label: "115 源目录",
                        variant: "outlined",
                        density: "comfortable",
                        readonly: "",
                        "hide-details": "",
                        onClick: $event => (openPicker('strm_source', index))
                      }, null, 8, ["modelValue", "onUpdate:modelValue", "onClick"]),
                      _createVNode(_component_v_text_field, {
                        modelValue: mapping.target_dir,
                        "onUpdate:modelValue": $event => ((mapping.target_dir) = $event),
                        label: "本地 STRM 输出目录",
                        variant: "outlined",
                        density: "comfortable",
                        readonly: "",
                        "hide-details": "",
                        onClick: $event => (openPicker('strm_target', index))
                      }, null, 8, ["modelValue", "onUpdate:modelValue", "onClick"]),
                      _createVNode(_component_v_tooltip, {
                        text: "删除映射",
                        location: "top"
                      }, {
                        activator: _withCtx(({ props: tipProps }) => [
                          _createVNode(_component_v_btn, _mergeProps({ ref_for: true }, tipProps, {
                            icon: "mdi-delete-outline",
                            variant: "text",
                            color: "error",
                            size: "small",
                            onClick: $event => (remove(config.strm_mappings, index))
                          }), null, 16, ["onClick"])
                        ]),
                        _: 2
                      }, 1024)
                    ]))
                  }), 128)),
                  (!config.strm_mappings.length)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_17, "尚未添加映射"))
                    : _createCommentVNode("", true),
                  _createVNode(_component_v_btn, {
                    class: "station-add",
                    variant: "text",
                    "prepend-icon": "mdi-plus",
                    onClick: addStrmMapping
                  }, {
                    default: _withCtx(() => [...(_cache[40] || (_cache[40] = [
                      _createTextVNode("添加 STRM 目录", -1)
                    ]))]),
                    _: 1
                  })
                ])
              ]),
              _: 1
            }),
            _createVNode(_component_v_window_item, { value: "upload" }, {
              default: _withCtx(() => [
                _createElementVNode("section", _hoisted_18, [
                  _cache[42] || (_cache[42] = _createElementVNode("div", null, [
                    _createElementVNode("span", { class: "work-code" }, "SYNC / UPLOAD"),
                    _createElementVNode("h3", null, "目录上传")
                  ], -1)),
                  _createElementVNode("div", _hoisted_19, [
                    _createVNode(_component_v_switch, {
                      modelValue: config.upload_include_sidecars,
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.upload_include_sidecars) = $event)),
                      label: "上传附属文件",
                      color: "primary",
                      "hide-details": "",
                      density: "compact",
                      class: "head-switch"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_switch, {
                      modelValue: config.upload_delete_source,
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.upload_delete_source) = $event)),
                      label: "上传完成后删除源文件",
                      color: "primary",
                      "hide-details": "",
                      density: "compact",
                      class: "head-switch"
                    }, null, 8, ["modelValue"])
                  ])
                ]),
                _createElementVNode("section", _hoisted_20, [
                  _createVNode(_component_v_text_field, {
                    modelValue: config.upload_media_extensions,
                    "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.upload_media_extensions) = $event)),
                    label: "媒体扩展名",
                    variant: "outlined",
                    density: "comfortable",
                    "hide-details": ""
                  }, null, 8, ["modelValue"]),
                  _createVNode(_component_v_text_field, {
                    modelValue: config.upload_sidecar_extensions,
                    "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.upload_sidecar_extensions) = $event)),
                    label: "附属文件扩展名",
                    variant: "outlined",
                    density: "comfortable",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode("div", _hoisted_21, [
                  _cache[44] || (_cache[44] = _createElementVNode("div", { class: "mapping-caption" }, [
                    _createElementVNode("span", null, "本地源目录"),
                    _createElementVNode("span", null, "115 目标目录")
                  ], -1)),
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(config.upload_mappings, (mapping, index) => {
                    return (_openBlock(), _createElementBlock("section", {
                      key: index,
                      class: "mapping-row"
                    }, [
                      _createVNode(_component_v_switch, {
                        modelValue: mapping.enabled,
                        "onUpdate:modelValue": $event => ((mapping.enabled) = $event),
                        "aria-label": "启用上传映射",
                        color: "primary",
                        "hide-details": "",
                        density: "compact"
                      }, null, 8, ["modelValue", "onUpdate:modelValue"]),
                      _createVNode(_component_v_text_field, {
                        modelValue: mapping.source,
                        "onUpdate:modelValue": $event => ((mapping.source) = $event),
                        label: "本地源目录",
                        variant: "outlined",
                        density: "comfortable",
                        readonly: "",
                        "hide-details": "",
                        onClick: $event => (openPicker('upload_source', index))
                      }, null, 8, ["modelValue", "onUpdate:modelValue", "onClick"]),
                      _createVNode(_component_v_text_field, {
                        modelValue: mapping.target,
                        "onUpdate:modelValue": $event => ((mapping.target) = $event),
                        label: "115 目标目录",
                        variant: "outlined",
                        density: "comfortable",
                        readonly: "",
                        "hide-details": "",
                        onClick: $event => (openPicker('upload_target', index))
                      }, null, 8, ["modelValue", "onUpdate:modelValue", "onClick"]),
                      _createVNode(_component_v_tooltip, {
                        text: "删除映射",
                        location: "top"
                      }, {
                        activator: _withCtx(({ props: tipProps }) => [
                          _createVNode(_component_v_btn, _mergeProps({ ref_for: true }, tipProps, {
                            icon: "mdi-delete-outline",
                            variant: "text",
                            color: "error",
                            size: "small",
                            onClick: $event => (remove(config.upload_mappings, index))
                          }), null, 16, ["onClick"])
                        ]),
                        _: 2
                      }, 1024)
                    ]))
                  }), 128)),
                  (!config.upload_mappings.length)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_22, "尚未添加上传目录"))
                    : _createCommentVNode("", true),
                  _createVNode(_component_v_btn, {
                    class: "station-add",
                    variant: "text",
                    "prepend-icon": "mdi-plus",
                    onClick: addUploadMapping
                  }, {
                    default: _withCtx(() => [...(_cache[43] || (_cache[43] = [
                      _createTextVNode("添加上传目录", -1)
                    ]))]),
                    _: 1
                  })
                ])
              ]),
              _: 1
            }),
            _createVNode(_component_v_window_item, { value: "checkin" }, {
              default: _withCtx(() => [
                _createElementVNode("section", _hoisted_23, [
                  _cache[45] || (_cache[45] = _createElementVNode("div", null, [
                    _createElementVNode("span", { class: "work-code" }, "PULSE / DAILY"),
                    _createElementVNode("h3", null, "每日签到")
                  ], -1)),
                  _createVNode(_component_v_switch, {
                    modelValue: config.checkin_enabled,
                    "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.checkin_enabled) = $event)),
                    label: "启用定时签到",
                    color: "primary",
                    "hide-details": "",
                    density: "compact",
                    class: "head-switch"
                  }, null, 8, ["modelValue"])
                ]),
                _createElementVNode("section", _hoisted_24, [
                  _createVNode(_component_v_text_field, {
                    modelValue: config.checkin_time_range,
                    "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.checkin_time_range) = $event)),
                    label: "签到时间段",
                    placeholder: "06:00-09:00",
                    variant: "outlined",
                    density: "comfortable",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ])
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        _createElementVNode("footer", _hoisted_25, [
          _createElementVNode("span", _hoisted_26, [
            _createElementVNode("i", {
              class: _normalizeClass({ live: config.enabled })
            }, null, 2),
            _createTextVNode(_toDisplayString(config.enabled ? '配置已启用' : '配置未启用'), 1)
          ]),
          _createElementVNode("div", null, [
            _createVNode(_component_v_btn, {
              class: "station-secondary",
              variant: "text",
              onClick: _cache[17] || (_cache[17] = $event => (applyConfig(props.initialConfig)))
            }, {
              default: _withCtx(() => [...(_cache[46] || (_cache[46] = [
                _createTextVNode("重置", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_btn, {
              class: "station-primary",
              loading: __props.saving,
              "prepend-icon": "mdi-content-save-outline",
              onClick: save
            }, {
              default: _withCtx(() => [...(_cache[47] || (_cache[47] = [
                _createTextVNode("保存更改", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ])
        ])
      ])
    ]),
    _createVNode(_component_v_dialog, {
      modelValue: qrDialog.open,
      "onUpdate:modelValue": [
        _cache[18] || (_cache[18] = $event => ((qrDialog.open) = $event)),
        _cache[19] || (_cache[19] = value => { if (!value) closeQrDialog(); })
      ],
      "max-width": "480"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, { class: "qr-login-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_27, [
              _createElementVNode("div", null, [
                _createVNode(_component_v_icon, {
                  icon: "mdi-qrcode",
                  size: "18"
                }),
                _cache[48] || (_cache[48] = _createElementVNode("span", null, "115网盘扫码登录", -1))
              ]),
              _createVNode(_component_v_btn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                onClick: closeQrDialog
              })
            ]),
            _createVNode(_component_v_card_text, { class: "qr-login-body" }, {
              default: _withCtx(() => [
                (qrDialog.error)
                  ? (_openBlock(), _createBlock(_component_v_alert, {
                      key: 0,
                      type: "error",
                      density: "compact",
                      variant: "tonal",
                      class: "mb-4"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(qrDialog.error), 1)
                      ]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                (qrDialog.loading)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_28, [
                      _createVNode(_component_v_progress_circular, {
                        indeterminate: "",
                        color: "primary",
                        size: "30"
                      }),
                      _cache[49] || (_cache[49] = _createElementVNode("span", null, "正在获取二维码", -1))
                    ]))
                  : (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                      _cache[51] || (_cache[51] = _createElementVNode("p", { class: "qr-login-label" }, "请选择扫码方式", -1)),
                      _createElementVNode("div", _hoisted_29, [
                        (_openBlock(), _createElementBlock(_Fragment, null, _renderList(qrClients, (client) => {
                          return _createVNode(_component_v_btn, {
                            key: client.value,
                            class: _normalizeClass({ selected: qrDialog.clientType === client.value }),
                            variant: "outlined",
                            size: "small",
                            onClick: $event => (selectQrClient(client.value))
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(client.label), 1)
                            ]),
                            _: 2
                          }, 1032, ["class", "onClick"])
                        }), 64))
                      ]),
                      (qrDialog.code)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_30, [
                            _createElementVNode("div", _hoisted_31, [
                              _createElementVNode("img", {
                                src: qrDialog.code,
                                alt: "115 登录二维码"
                              }, null, 8, _hoisted_32)
                            ]),
                            _createElementVNode("p", null, "请使用" + _toDisplayString(selectedQrClient.value.label) + "扫描二维码登录", 1),
                            _createElementVNode("strong", null, _toDisplayString(qrDialog.status), 1),
                            _createVNode(_component_v_btn, {
                              class: "qr-refresh",
                              "prepend-icon": "mdi-refresh",
                              size: "small",
                              onClick: refreshQrCode
                            }, {
                              default: _withCtx(() => [...(_cache[50] || (_cache[50] = [
                                _createTextVNode("刷新二维码", -1)
                              ]))]),
                              _: 1
                            })
                          ]))
                        : _createCommentVNode("", true)
                    ], 64))
              ]),
              _: 1
            }),
            _createVNode(_component_v_divider),
            _createVNode(_component_v_card_actions, { class: "qr-login-actions" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_btn, {
                  "prepend-icon": "mdi-close",
                  variant: "text",
                  onClick: closeQrDialog
                }, {
                  default: _withCtx(() => [...(_cache[52] || (_cache[52] = [
                    _createTextVNode("关闭", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  "prepend-icon": "mdi-refresh",
                  variant: "text",
                  disabled: qrDialog.loading,
                  onClick: refreshQrCode
                }, {
                  default: _withCtx(() => [...(_cache[53] || (_cache[53] = [
                    _createTextVNode("刷新二维码", -1)
                  ]))]),
                  _: 1
                }, 8, ["disabled"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: picker.open,
      "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((picker.open) = $event)),
      "max-width": "760"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, { class: "picker-dialog" }, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_33, [
              _createElementVNode("span", null, _toDisplayString(pickerTitle.value), 1),
              _createVNode(_component_v_btn, {
                icon: "mdi-close",
                variant: "text",
                size: "small",
                onClick: _cache[20] || (_cache[20] = $event => (picker.open = false))
              })
            ]),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_34, [
                  _createVNode(_component_v_btn, {
                    icon: "mdi-arrow-up",
                    variant: "text",
                    size: "small",
                    disabled: isRemotePicker.value ? !picker.remoteTrail.length : !picker.path,
                    title: "上级目录",
                    onClick: pickerBack
                  }, null, 8, ["disabled"]),
                  _createElementVNode("span", _hoisted_35, _toDisplayString(isRemotePicker.value ? `/${picker.remoteTrail.map(item => item.name).join('/')}` || '/' : picker.path || picker.localBase || '/'), 1)
                ]),
                (!isRemotePicker.value && picker.roots.length > 1)
                  ? (_openBlock(), _createBlock(_component_v_select, {
                      key: 0,
                      "model-value": picker.localBase,
                      items: picker.roots,
                      "item-title": "name",
                      "item-value": "path",
                      label: "本地根目录",
                      variant: "outlined",
                      density: "compact",
                      "hide-details": "",
                      class: "picker-root",
                      "onUpdate:modelValue": switchLocalRoot
                    }, null, 8, ["model-value", "items"]))
                  : _createCommentVNode("", true),
                _createVNode(_component_v_list, {
                  density: "compact",
                  lines: "one",
                  class: "picker-list"
                }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(picker.items, (item) => {
                      return (_openBlock(), _createBlock(_component_v_list_item, {
                        key: item.cid || item.path,
                        "prepend-icon": "mdi-folder-outline",
                        title: item.name,
                        onClick: $event => (browsePicker(item))
                      }, null, 8, ["title", "onClick"]))
                    }), 128))
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_actions, { class: "picker-actions" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  class: "station-secondary",
                  onClick: _cache[21] || (_cache[21] = $event => (picker.open = false))
                }, {
                  default: _withCtx(() => [...(_cache[54] || (_cache[54] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  class: "station-primary",
                  onClick: selectPicker
                }, {
                  default: _withCtx(() => [...(_cache[55] || (_cache[55] = [
                    _createTextVNode("选择当前目录", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-c3e0c4a1"]]);

export { Config as default };
