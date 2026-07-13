import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginRequest } from './_plugin-vue_export-helper-75e59c87.js';

const AuthPanel_vue_vue_type_style_index_0_scoped_ea378f22_lang = '';

const {createElementVNode:_createElementVNode$3,resolveComponent:_resolveComponent$3,createVNode:_createVNode$3,createTextVNode:_createTextVNode$3,withCtx:_withCtx$3,openBlock:_openBlock$3,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$3,createElementBlock:_createElementBlock$3,vShow:_vShow,withDirectives:_withDirectives} = await importShared('vue');


const _hoisted_1$3 = { class: "auth-panel" };
const _hoisted_2$2 = {
  key: 1,
  class: "qrcode-box"
};
const _hoisted_3$1 = { class: "qrcode-actions" };
const _hoisted_4$1 = {
  key: 0,
  class: "qrcode-image-container"
};
const _hoisted_5$1 = ["src"];

const {reactive,ref: ref$3} = await importShared('vue');


const _sfc_main$3 = {
  __name: 'AuthPanel',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
  config: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['update:config', 'toast'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = reactive({ qrcode: false, check: false });
const qrcodeImage = ref$3('');
const qrcodeText = ref$3('');

function update(key, value) {
  emit('update:config', { ...props.config, [key]: value });
}

async function generateQrcode() {
  loading.qrcode = true;
  try {
    const result = await pluginRequest(props.api, '/qrcode', { method: 'POST' });
    if (!result?.success) throw new Error(result?.message || '生成二维码失败')
    qrcodeImage.value = result?.data?.qrcode || '';
    qrcodeText.value = result?.data?.codeContent || '';
    emit('toast', '二维码已生成，请用手机 115 APP 扫描');
  } catch (error) {
    emit('toast', error?.message || '生成二维码失败', 'error');
    qrcodeImage.value = '';
    qrcodeText.value = '';
  } finally {
    loading.qrcode = false;
  }
}

async function checkLogin() {
  loading.check = true;
  try {
    const result = await pluginRequest(props.api, '/check_login');
    if (!result?.success) throw new Error(result?.message || '登录未完成')
    emit('toast', result?.data?.tip || '登录状态已更新');
  } catch (error) {
    emit('toast', error?.message || '检查登录失败', 'error');
  } finally {
    loading.check = false;
  }
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$3("v-icon");
  const _component_v_btn = _resolveComponent$3("v-btn");
  const _component_v_btn_toggle = _resolveComponent$3("v-btn-toggle");
  const _component_v_textarea = _resolveComponent$3("v-textarea");

  return (_openBlock$3(), _createElementBlock$3("section", _hoisted_1$3, [
    _cache[8] || (_cache[8] = _createElementVNode$3("div", { class: "section-title" }, "115 授权", -1)),
    _createVNode$3(_component_v_btn_toggle, {
      "model-value": __props.config.auth_mode,
      mandatory: "",
      color: "#167A5B",
      variant: "outlined",
      density: "comfortable",
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => (update('auth_mode', $event)))
    }, {
      default: _withCtx$3(() => [
        _createVNode$3(_component_v_btn, { value: "cookie" }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_icon, {
              icon: "mdi-cookie-outline",
              class: "mr-1"
            }),
            _cache[3] || (_cache[3] = _createTextVNode$3("Cookie", -1))
          ]),
          _: 1
        }),
        _createVNode$3(_component_v_btn, { value: "qrcode" }, {
          default: _withCtx$3(() => [
            _createVNode$3(_component_v_icon, {
              icon: "mdi-qrcode-scan",
              class: "mr-1"
            }),
            _cache[4] || (_cache[4] = _createTextVNode$3("扫码", -1))
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["model-value"]),
    (__props.config.auth_mode === 'cookie')
      ? (_openBlock$3(), _createBlock$2(_component_v_textarea, {
          key: 0,
          "model-value": __props.config.cookie,
          label: "115 Cookie",
          variant: "outlined",
          rows: "4",
          "auto-grow": "",
          "hide-details": "",
          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => (update('cookie', $event)))
        }, null, 8, ["model-value"]))
      : (_openBlock$3(), _createElementBlock$3("div", _hoisted_2$2, [
          _createElementVNode$3("div", _hoisted_3$1, [
            _createVNode$3(_component_v_btn, {
              color: "#167A5B",
              variant: "flat",
              loading: loading.qrcode,
              onClick: generateQrcode
            }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_icon, {
                  icon: "mdi-qrcode-plus",
                  class: "mr-1"
                }),
                _cache[5] || (_cache[5] = _createTextVNode$3("生成二维码 ", -1))
              ]),
              _: 1
            }, 8, ["loading"]),
            _createVNode$3(_component_v_btn, {
              color: "#245B7A",
              variant: "tonal",
              loading: loading.check,
              onClick: checkLogin
            }, {
              default: _withCtx$3(() => [
                _createVNode$3(_component_v_icon, {
                  icon: "mdi-check-circle-outline",
                  class: "mr-1"
                }),
                _cache[6] || (_cache[6] = _createTextVNode$3("检查登录 ", -1))
              ]),
              _: 1
            }, 8, ["loading"])
          ]),
          (qrcodeImage.value)
            ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_4$1, [
                _createElementVNode$3("img", {
                  src: qrcodeImage.value,
                  alt: "115 登录二维码",
                  class: "qrcode-image"
                }, null, 8, _hoisted_5$1),
                _cache[7] || (_cache[7] = _createElementVNode$3("p", { class: "qrcode-hint" }, "用手机 115 APP 扫描上方二维码登录", -1))
              ]))
            : _createCommentVNode$3("", true),
          _withDirectives(_createVNode$3(_component_v_textarea, {
            modelValue: qrcodeText.value,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((qrcodeText).value = $event)),
            label: "二维码内容（备用）",
            variant: "outlined",
            rows: "2",
            readonly: "",
            "hide-details": "",
            density: "compact",
            class: "mt-2"
          }, null, 8, ["modelValue"]), [
            [_vShow, qrcodeText.value]
          ])
        ]))
  ]))
}
}

};
const AuthPanel = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-ea378f22"]]);

const LocalPathSelector_vue_vue_type_style_index_0_scoped_f72b39f6_lang = '';

const {createElementVNode:_createElementVNode$2,resolveComponent:_resolveComponent$2,createVNode:_createVNode$2,withCtx:_withCtx$2,toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$2,withModifiers:_withModifiers,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createCommentVNode:_createCommentVNode$2,createBlock:_createBlock$1,renderList:_renderList$2,Fragment:_Fragment$2} = await importShared('vue');


const _hoisted_1$2 = {
  key: 0,
  class: "breadcrumb-bar mb-4"
};

const {ref: ref$2,watch: watch$1} = await importShared('vue');


const _sfc_main$2 = {
  __name: 'LocalPathSelector',
  props: {
  modelValue: {
    type: Boolean,
    default: false,
  },
  api: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['update:modelValue', 'selected', 'toast'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = ref$2(false);
const basePath = ref$2('');
const currentPath = ref$2('');
const items = ref$2([]);
const breadcrumbs = ref$2([]);

async function loadDirectory(path = '') {
  loading.value = true;
  try {
    const queryPath = path ? `?path=${encodeURIComponent(path)}` : '';
    const result = await pluginRequest(props.api, `/browse_local${queryPath}`, { method: 'GET' });

    if (!result?.success) {
      emit('toast', result?.msg || '获取目录失败', 'error');
      return
    }

    basePath.value = result.data.base;
    currentPath.value = result.data.current || '';
    items.value = result.data.items || [];

    // 更新面包屑
    updateBreadcrumbs(path);
  } catch (error) {
    emit('toast', error?.message || '获取目录失败', 'error');
  } finally {
    loading.value = false;
  }
}

function updateBreadcrumbs(path) {
  breadcrumbs.value = [{ name: '媒体库', path: '' }];

  if (path) {
    const parts = path.split('/').filter(Boolean);
    let currentBreadPath = '';
    for (const part of parts) {
      currentBreadPath += (currentBreadPath ? '/' : '') + part;
      breadcrumbs.value.push({ name: part, path: currentBreadPath });
    }
  }
}

function navigateToDirectory(item) {
  loadDirectory(item.path);
}

function navigateToBreadcrumb(breadcrumb) {
  loadDirectory(breadcrumb.path);
}

function selectCurrentDirectory() {
  const fullPath = currentPath.value ? currentPath.value : '';
  emit('selected', fullPath);
  emit('update:modelValue', false);
}

function closeDialog() {
  emit('update:modelValue', false);
}

watch$1(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen) {
      loadDirectory('');
    }
  }
);

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$2("v-icon");
  const _component_v_card_title = _resolveComponent$2("v-card-title");
  const _component_v_divider = _resolveComponent$2("v-divider");
  const _component_v_breadcrumbs_item = _resolveComponent$2("v-breadcrumbs-item");
  const _component_v_breadcrumbs = _resolveComponent$2("v-breadcrumbs");
  const _component_v_progress_linear = _resolveComponent$2("v-progress-linear");
  const _component_v_list_item = _resolveComponent$2("v-list-item");
  const _component_v_list_item_title = _resolveComponent$2("v-list-item-title");
  const _component_v_list = _resolveComponent$2("v-list");
  const _component_v_card_text = _resolveComponent$2("v-card-text");
  const _component_v_spacer = _resolveComponent$2("v-spacer");
  const _component_v_btn = _resolveComponent$2("v-btn");
  const _component_v_card_actions = _resolveComponent$2("v-card-actions");
  const _component_v_card = _resolveComponent$2("v-card");
  const _component_v_dialog = _resolveComponent$2("v-dialog");

  return (_openBlock$2(), _createBlock$1(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": "600px",
    persistent: "",
    "onUpdate:modelValue": closeDialog
  }, {
    default: _withCtx$2(() => [
      _createVNode$2(_component_v_card, { class: "local-path-selector" }, {
        default: _withCtx$2(() => [
          _createVNode$2(_component_v_card_title, { class: "d-flex align-center justify-space-between" }, {
            default: _withCtx$2(() => [
              _cache[0] || (_cache[0] = _createElementVNode$2("span", null, "选择本地目录", -1)),
              _createVNode$2(_component_v_icon, { icon: "mdi-folder-outline" })
            ]),
            _: 1
          }),
          _createVNode$2(_component_v_divider),
          _createVNode$2(_component_v_card_text, { class: "pa-4" }, {
            default: _withCtx$2(() => [
              (breadcrumbs.value.length > 0)
                ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_1$2, [
                    _createVNode$2(_component_v_breadcrumbs, {
                      items: breadcrumbs.value,
                      small: ""
                    }, {
                      item: _withCtx$2(({ item, index }) => [
                        _createVNode$2(_component_v_breadcrumbs_item, {
                          href: `#`,
                          onClick: _withModifiers($event => (navigateToBreadcrumb(item)), ["prevent"]),
                          disabled: loading.value
                        }, {
                          default: _withCtx$2(() => [
                            _createTextVNode$2(_toDisplayString$1(item.name), 1)
                          ]),
                          _: 2
                        }, 1032, ["onClick", "disabled"])
                      ]),
                      _: 1
                    }, 8, ["items"])
                  ]))
                : _createCommentVNode$2("", true),
              (loading.value)
                ? (_openBlock$2(), _createBlock$1(_component_v_progress_linear, {
                    key: 1,
                    indeterminate: "",
                    class: "mb-3"
                  }))
                : (_openBlock$2(), _createBlock$1(_component_v_list, {
                    key: 2,
                    density: "compact",
                    class: "directory-list"
                  }, {
                    default: _withCtx$2(() => [
                      (items.value.length === 0)
                        ? (_openBlock$2(), _createBlock$1(_component_v_list_item, {
                            key: 0,
                            disabled: "",
                            class: "text-center text-grey"
                          }, {
                            default: _withCtx$2(() => [...(_cache[1] || (_cache[1] = [
                              _createElementVNode$2("span", null, "此目录为空", -1)
                            ]))]),
                            _: 1
                          }))
                        : _createCommentVNode$2("", true),
                      (_openBlock$2(true), _createElementBlock$2(_Fragment$2, null, _renderList$2(items.value, (item) => {
                        return (_openBlock$2(), _createBlock$1(_component_v_list_item, {
                          key: item.path,
                          onClick: $event => (navigateToDirectory(item)),
                          class: "directory-item"
                        }, {
                          prepend: _withCtx$2(() => [
                            _createVNode$2(_component_v_icon, {
                              icon: "mdi-folder",
                              color: "#167A5B"
                            })
                          ]),
                          append: _withCtx$2(() => [
                            _createVNode$2(_component_v_icon, {
                              icon: "mdi-chevron-right",
                              size: "small",
                              color: "#999"
                            })
                          ]),
                          default: _withCtx$2(() => [
                            _createVNode$2(_component_v_list_item_title, null, {
                              default: _withCtx$2(() => [
                                _createTextVNode$2(_toDisplayString$1(item.name), 1)
                              ]),
                              _: 2
                            }, 1024)
                          ]),
                          _: 2
                        }, 1032, ["onClick"]))
                      }), 128))
                    ]),
                    _: 1
                  }))
            ]),
            _: 1
          }),
          _createVNode$2(_component_v_divider),
          _createVNode$2(_component_v_card_actions, { class: "pa-4" }, {
            default: _withCtx$2(() => [
              _createVNode$2(_component_v_spacer),
              _createVNode$2(_component_v_btn, {
                variant: "plain",
                onClick: closeDialog,
                disabled: loading.value
              }, {
                default: _withCtx$2(() => [...(_cache[2] || (_cache[2] = [
                  _createTextVNode$2(" 取消 ", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$2(_component_v_btn, {
                color: "#167A5B",
                variant: "flat",
                onClick: selectCurrentDirectory,
                disabled: loading.value
              }, {
                default: _withCtx$2(() => [...(_cache[3] || (_cache[3] = [
                  _createTextVNode$2(" 选择当前目录 ", -1)
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
  }, 8, ["model-value"]))
}
}

};
const LocalPathSelector = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-f72b39f6"]]);

const P115PathSelector_vue_vue_type_style_index_0_scoped_1e32f711_lang = '';

const {createElementVNode:_createElementVNode$1,resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,withCtx:_withCtx$1,toDisplayString:_toDisplayString,openBlock:_openBlock$1,createBlock:_createBlock,createCommentVNode:_createCommentVNode$1,renderList:_renderList$1,Fragment:_Fragment$1,createElementBlock:_createElementBlock$1,createTextVNode:_createTextVNode$1} = await importShared('vue');


const _hoisted_1$1 = { class: "breadcrumb-bar mb-4" };
const _hoisted_2$1 = { class: "breadcrumb-text" };

const {ref: ref$1,watch} = await importShared('vue');


const _sfc_main$1 = {
  __name: 'P115PathSelector',
  props: {
  modelValue: {
    type: Boolean,
    default: false,
  },
  api: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['update:modelValue', 'selected', 'toast'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const ROOT_BREADCRUMB = { cid: '0', name: '115云盘' };

const loading = ref$1(false);
const refreshing = ref$1(false);
const items = ref$1([]);
const breadcrumbs = ref$1([{ ...ROOT_BREADCRUMB }]);

/**
 * 加载指定目录的内容。
 * 仅负责拉取并渲染列表与加载状态，不修改面包屑；
 * 面包屑由 navigateToDirectory / goBack 独立维护。
 */
async function loadDirectory(cid = '0', isRefresh = false) {
  if (isRefresh) {
    refreshing.value = true;
  } else {
    loading.value = true;
  }

  try {
    const refreshParam = isRefresh ? '&refresh=true' : '';
    const result = await pluginRequest(
      props.api,
      `/browse_115?cid=${encodeURIComponent(cid)}${refreshParam}`,
      { method: 'GET' }
    );

    if (!result?.success) {
      emit('toast', result?.msg || '获取目录失败', 'error');
      return false
    }

    items.value = result.data?.items || [];

    if (isRefresh) {
      emit('toast', '目录已刷新', 'success');
    }
    return true
  } catch (error) {
    emit('toast', error?.message || '获取目录失败', 'error');
    return false
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

async function navigateToDirectory(item) {
  if (!item?.cid) {
    return
  }
  // 先入栈面包屑再加载；加载失败则回退，保持面包屑与列表一致。
  breadcrumbs.value.push({ cid: item.cid, name: item.name || `文件夹 ${item.cid}` });
  const ok = await loadDirectory(item.cid, false);
  if (!ok) {
    breadcrumbs.value.pop();
  }
}

function goBack() {
  if (breadcrumbs.value.length > 1) {
    breadcrumbs.value.pop();
    const currentCid = breadcrumbs.value[breadcrumbs.value.length - 1].cid;
    loadDirectory(currentCid, false);
  }
}

function refresh() {
  const currentCid = breadcrumbs.value[breadcrumbs.value.length - 1].cid;
  loadDirectory(currentCid, true);
}

function selectCurrentDirectory() {
  const current = breadcrumbs.value[breadcrumbs.value.length - 1];
  emit('selected', current.cid, current.name);
  emit('update:modelValue', false);
  breadcrumbs.value = [{ ...ROOT_BREADCRUMB }];
}

function closeDialog() {
  emit('update:modelValue', false);
  breadcrumbs.value = [{ ...ROOT_BREADCRUMB }];
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen) {
      loadDirectory('0', false);
    }
  }
);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_card_title = _resolveComponent$1("v-card-title");
  const _component_v_divider = _resolveComponent$1("v-divider");
  const _component_v_progress_linear = _resolveComponent$1("v-progress-linear");
  const _component_v_list_item = _resolveComponent$1("v-list-item");
  const _component_v_icon = _resolveComponent$1("v-icon");
  const _component_v_list_item_title = _resolveComponent$1("v-list-item-title");
  const _component_v_list = _resolveComponent$1("v-list");
  const _component_v_card_text = _resolveComponent$1("v-card-text");
  const _component_v_spacer = _resolveComponent$1("v-spacer");
  const _component_v_card_actions = _resolveComponent$1("v-card-actions");
  const _component_v_card = _resolveComponent$1("v-card");
  const _component_v_dialog = _resolveComponent$1("v-dialog");

  return (_openBlock$1(), _createBlock(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": "600px",
    persistent: "",
    "onUpdate:modelValue": closeDialog
  }, {
    default: _withCtx$1(() => [
      _createVNode$1(_component_v_card, { class: "p115-path-selector" }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_v_card_title, { class: "d-flex align-center justify-space-between" }, {
            default: _withCtx$1(() => [
              _cache[0] || (_cache[0] = _createElementVNode$1("span", null, "选择 115 云盘目录", -1)),
              _createVNode$1(_component_v_btn, {
                icon: "mdi-refresh",
                size: "small",
                variant: "text",
                loading: refreshing.value,
                disabled: loading.value || refreshing.value,
                onClick: refresh,
                title: "刷新目录缓存"
              }, null, 8, ["loading", "disabled"])
            ]),
            _: 1
          }),
          _createVNode$1(_component_v_divider),
          _createVNode$1(_component_v_card_text, { class: "pa-4" }, {
            default: _withCtx$1(() => [
              _createElementVNode$1("div", _hoisted_1$1, [
                _createVNode$1(_component_v_btn, {
                  icon: "mdi-arrow-left",
                  size: "small",
                  variant: "text",
                  disabled: breadcrumbs.value.length <= 1 || loading.value,
                  onClick: goBack,
                  title: "返回上一级"
                }, null, 8, ["disabled"]),
                _createElementVNode$1("span", _hoisted_2$1, _toDisplayString(breadcrumbs.value.map(b => b.name).join(' / ')), 1)
              ]),
              (loading.value)
                ? (_openBlock$1(), _createBlock(_component_v_progress_linear, {
                    key: 0,
                    indeterminate: "",
                    class: "mb-3"
                  }))
                : (_openBlock$1(), _createBlock(_component_v_list, {
                    key: 1,
                    density: "compact",
                    class: "directory-list"
                  }, {
                    default: _withCtx$1(() => [
                      (items.value.length === 0)
                        ? (_openBlock$1(), _createBlock(_component_v_list_item, {
                            key: 0,
                            disabled: "",
                            class: "text-center text-grey"
                          }, {
                            default: _withCtx$1(() => [...(_cache[1] || (_cache[1] = [
                              _createElementVNode$1("span", null, "此目录为空", -1)
                            ]))]),
                            _: 1
                          }))
                        : _createCommentVNode$1("", true),
                      (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(items.value, (item) => {
                        return (_openBlock$1(), _createBlock(_component_v_list_item, {
                          key: item.cid,
                          onClick: $event => (navigateToDirectory(item)),
                          class: "directory-item"
                        }, {
                          prepend: _withCtx$1(() => [
                            _createVNode$1(_component_v_icon, {
                              icon: "mdi-folder",
                              color: "#245B7A"
                            })
                          ]),
                          append: _withCtx$1(() => [
                            _createVNode$1(_component_v_icon, {
                              icon: "mdi-chevron-right",
                              size: "small",
                              color: "#999"
                            })
                          ]),
                          default: _withCtx$1(() => [
                            _createVNode$1(_component_v_list_item_title, null, {
                              default: _withCtx$1(() => [
                                _createTextVNode$1(_toDisplayString(item.name), 1)
                              ]),
                              _: 2
                            }, 1024)
                          ]),
                          _: 2
                        }, 1032, ["onClick"]))
                      }), 128))
                    ]),
                    _: 1
                  }))
            ]),
            _: 1
          }),
          _createVNode$1(_component_v_divider),
          _createVNode$1(_component_v_card_actions, { class: "pa-4" }, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_v_spacer),
              _createVNode$1(_component_v_btn, {
                variant: "plain",
                onClick: closeDialog,
                disabled: loading.value
              }, {
                default: _withCtx$1(() => [...(_cache[2] || (_cache[2] = [
                  _createTextVNode$1(" 取消 ", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$1(_component_v_btn, {
                color: "#245B7A",
                variant: "flat",
                onClick: selectCurrentDirectory,
                disabled: loading.value
              }, {
                default: _withCtx$1(() => [...(_cache[3] || (_cache[3] = [
                  _createTextVNode$1(" 选择当前目录 ", -1)
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
  }, 8, ["model-value"]))
}
}

};
const P115PathSelector = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-1e32f711"]]);

const PathMappingEditor_vue_vue_type_style_index_0_scoped_ed80e65f_lang = '';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "mapping-editor" };
const _hoisted_2 = { class: "mapping-editor__head" };
const _hoisted_3 = {
  key: 0,
  class: "empty-line"
};
const _hoisted_4 = {
  key: 1,
  class: "mappings-list"
};
const _hoisted_5 = { class: "path-field" };
const _hoisted_6 = { class: "path-field" };
const _hoisted_7 = {
  key: 2,
  class: "mapping-actions mt-3"
};

const {ref} = await importShared('vue');


const _sfc_main = {
  __name: 'PathMappingEditor',
  props: {
  api: Object,
  mappings: {
    type: Array,
    default: () => [],
  },
},
  emits: ['update:mappings', 'toast'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const localPathDialogOpen = ref(false);
const p115PathDialogOpen = ref(false);
const editingIndex = ref(null);
const savingMappings = ref(false);

function addMapping() {
  emit('update:mappings', [
    ...props.mappings,
    {
      enabled: true,
      source: '',
      sourceDesc: '',
      target: '/',
      targetCid: '0',
    },
  ]);
}

function removeMapping(index) {
  emit('update:mappings', props.mappings.filter((_, idx) => idx !== index));
}

function toggleMapping(index) {
  const updated = [...props.mappings];
  updated[index].enabled = !updated[index].enabled;
  emit('update:mappings', updated);
}

function openLocalPathSelector(index) {
  editingIndex.value = index;
  localPathDialogOpen.value = true;
}

function onLocalPathSelected(path) {
  if (editingIndex.value === null) return

  const mapping = props.mappings[editingIndex.value];
  const updated = [...props.mappings];
  const displayName = path.split('/').pop() || path || '媒体库';

  updated[editingIndex.value] = {
    ...mapping,
    source: path,
    sourceDesc: displayName,
  };

  emit('update:mappings', updated);
  localPathDialogOpen.value = false;
  editingIndex.value = null;
}

function openP115PathSelector(index) {
  editingIndex.value = index;
  p115PathDialogOpen.value = true;
}

function onP115PathSelected(cid, name) {
  if (editingIndex.value === null) return

  const mapping = props.mappings[editingIndex.value];
  const updated = [...props.mappings];

  updated[editingIndex.value] = {
    ...mapping,
    target: name,
    targetCid: cid,
  };

  emit('update:mappings', updated);
  p115PathDialogOpen.value = false;
  editingIndex.value = null;
}

async function saveMappings() {
  savingMappings.value = true;
  try {
    const result = await pluginRequest(props.api, '/path_mappings', {
      method: 'POST',
      body: props.mappings,
    });

    if (!result?.success) {
      emit('toast', result?.msg || '保存失败', 'error');
      return
    }

    emit('toast', '路径映射已保存', 'success');
  } catch (error) {
    emit('toast', error?.message || '保存失败', 'error');
  } finally {
    savingMappings.value = false;
  }
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_text_field = _resolveComponent("v-text-field");

  return (_openBlock(), _createElementBlock("section", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[5] || (_cache[5] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "section-title" }, "路径映射"),
        _createElementVNode("div", { class: "section-subtitle" }, "本地目录上传到对应 115 目录")
      ], -1)),
      _createVNode(_component_v_btn, {
        color: "#167A5B",
        variant: "flat",
        size: "small",
        onClick: addMapping
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_icon, {
            icon: "mdi-plus",
            class: "mr-1"
          }),
          _cache[4] || (_cache[4] = _createTextVNode("新增 ", -1))
        ]),
        _: 1
      })
    ]),
    (!__props.mappings.length)
      ? (_openBlock(), _createElementBlock("div", _hoisted_3, "暂无路径映射"))
      : (_openBlock(), _createElementBlock("div", _hoisted_4, [
          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(__props.mappings, (mapping, index) => {
            return (_openBlock(), _createElementBlock("div", {
              key: index,
              class: "mapping-row"
            }, [
              _createVNode(_component_v_switch, {
                "model-value": mapping.enabled,
                color: "#167A5B",
                density: "compact",
                "hide-details": "",
                inset: "",
                "onUpdate:modelValue": $event => (toggleMapping(index)),
                class: "mapping-switch"
              }, null, 8, ["model-value", "onUpdate:modelValue"]),
              _createElementVNode("div", _hoisted_5, [
                _createVNode(_component_v_text_field, {
                  "model-value": mapping.sourceDesc || mapping.source || '未选择',
                  label: "本地目录",
                  variant: "outlined",
                  density: "compact",
                  "hide-details": "",
                  readonly: "",
                  "prepend-inner-icon": "mdi-folder-outline",
                  class: "path-input"
                }, null, 8, ["model-value"]),
                _createVNode(_component_v_btn, {
                  icon: "mdi-folder-open-outline",
                  size: "small",
                  variant: "text",
                  color: "#167A5B",
                  onClick: $event => (openLocalPathSelector(index)),
                  title: "浏览本地目录"
                }, null, 8, ["onClick"])
              ]),
              _createElementVNode("div", _hoisted_6, [
                _createVNode(_component_v_text_field, {
                  "model-value": mapping.target || '未选择',
                  label: "115 目录",
                  variant: "outlined",
                  density: "compact",
                  "hide-details": "",
                  readonly: "",
                  "prepend-inner-icon": "mdi-cloud-outline",
                  class: "path-input"
                }, null, 8, ["model-value"]),
                _createVNode(_component_v_btn, {
                  icon: "mdi-cloud-search-outline",
                  size: "small",
                  variant: "text",
                  color: "#245B7A",
                  onClick: $event => (openP115PathSelector(index)),
                  title: "浏览 115 目录"
                }, null, 8, ["onClick"])
              ]),
              _createVNode(_component_v_btn, {
                icon: "mdi-delete-outline",
                size: "small",
                variant: "text",
                color: "#B42318",
                onClick: $event => (removeMapping(index)),
                title: "删除此映射"
              }, null, 8, ["onClick"])
            ]))
          }), 128))
        ])),
    (__props.mappings.length)
      ? (_openBlock(), _createElementBlock("div", _hoisted_7, [
          _createVNode(_component_v_btn, {
            color: "#167A5B",
            variant: "flat",
            loading: savingMappings.value,
            onClick: saveMappings
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                icon: "mdi-content-save",
                class: "mr-1"
              }),
              _cache[6] || (_cache[6] = _createTextVNode("保存映射 ", -1))
            ]),
            _: 1
          }, 8, ["loading"])
        ]))
      : _createCommentVNode("", true),
    _createVNode(LocalPathSelector, {
      modelValue: localPathDialogOpen.value,
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((localPathDialogOpen).value = $event)),
      api: __props.api,
      onSelected: onLocalPathSelected,
      onToast: _cache[1] || (_cache[1] = (msg, type) => _ctx.$emit('toast', msg, type))
    }, null, 8, ["modelValue", "api"]),
    _createVNode(P115PathSelector, {
      modelValue: p115PathDialogOpen.value,
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((p115PathDialogOpen).value = $event)),
      api: __props.api,
      onSelected: onP115PathSelected,
      onToast: _cache[3] || (_cache[3] = (msg, type) => _ctx.$emit('toast', msg, type))
    }, null, 8, ["modelValue", "api"])
  ]))
}
}

};
const PathMappingEditor = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-ed80e65f"]]);

export { AuthPanel as A, PathMappingEditor as P };
