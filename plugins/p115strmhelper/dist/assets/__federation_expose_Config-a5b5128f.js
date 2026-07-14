import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc, p as pluginRequest } from './_plugin-vue_export-helper-59eae27f.js';

const AuthPanel_vue_vue_type_style_index_0_scoped_ea378f22_lang = '';

const {createElementVNode:_createElementVNode$5,resolveComponent:_resolveComponent$5,createVNode:_createVNode$5,createTextVNode:_createTextVNode$4,withCtx:_withCtx$4,openBlock:_openBlock$5,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$3,createElementBlock:_createElementBlock$5,vShow:_vShow,withDirectives:_withDirectives} = await importShared('vue');


const _hoisted_1$5 = { class: "auth-panel" };
const _hoisted_2$4 = {
  key: 1,
  class: "qrcode-box"
};
const _hoisted_3$1 = { class: "qrcode-actions" };
const _hoisted_4$1 = {
  key: 0,
  class: "qrcode-image-container"
};
const _hoisted_5$1 = ["src"];

const {reactive: reactive$1,ref: ref$3} = await importShared('vue');


const _sfc_main$5 = {
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

const loading = reactive$1({ qrcode: false, check: false });
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
  const _component_v_icon = _resolveComponent$5("v-icon");
  const _component_v_btn = _resolveComponent$5("v-btn");
  const _component_v_btn_toggle = _resolveComponent$5("v-btn-toggle");
  const _component_v_textarea = _resolveComponent$5("v-textarea");

  return (_openBlock$5(), _createElementBlock$5("section", _hoisted_1$5, [
    _cache[8] || (_cache[8] = _createElementVNode$5("div", { class: "section-title" }, "115 授权", -1)),
    _createVNode$5(_component_v_btn_toggle, {
      "model-value": __props.config.auth_mode,
      mandatory: "",
      color: "#167A5B",
      variant: "outlined",
      density: "comfortable",
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => (update('auth_mode', $event)))
    }, {
      default: _withCtx$4(() => [
        _createVNode$5(_component_v_btn, { value: "cookie" }, {
          default: _withCtx$4(() => [
            _createVNode$5(_component_v_icon, {
              icon: "mdi-cookie-outline",
              class: "mr-1"
            }),
            _cache[3] || (_cache[3] = _createTextVNode$4("Cookie", -1))
          ]),
          _: 1
        }),
        _createVNode$5(_component_v_btn, { value: "qrcode" }, {
          default: _withCtx$4(() => [
            _createVNode$5(_component_v_icon, {
              icon: "mdi-qrcode-scan",
              class: "mr-1"
            }),
            _cache[4] || (_cache[4] = _createTextVNode$4("扫码", -1))
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["model-value"]),
    (__props.config.auth_mode === 'cookie')
      ? (_openBlock$5(), _createBlock$2(_component_v_textarea, {
          key: 0,
          "model-value": __props.config.cookie,
          label: "115 Cookie",
          variant: "outlined",
          rows: "4",
          "auto-grow": "",
          "hide-details": "",
          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => (update('cookie', $event)))
        }, null, 8, ["model-value"]))
      : (_openBlock$5(), _createElementBlock$5("div", _hoisted_2$4, [
          _createElementVNode$5("div", _hoisted_3$1, [
            _createVNode$5(_component_v_btn, {
              color: "#167A5B",
              variant: "flat",
              loading: loading.qrcode,
              onClick: generateQrcode
            }, {
              default: _withCtx$4(() => [
                _createVNode$5(_component_v_icon, {
                  icon: "mdi-qrcode-plus",
                  class: "mr-1"
                }),
                _cache[5] || (_cache[5] = _createTextVNode$4("生成二维码 ", -1))
              ]),
              _: 1
            }, 8, ["loading"]),
            _createVNode$5(_component_v_btn, {
              color: "#245B7A",
              variant: "tonal",
              loading: loading.check,
              onClick: checkLogin
            }, {
              default: _withCtx$4(() => [
                _createVNode$5(_component_v_icon, {
                  icon: "mdi-check-circle-outline",
                  class: "mr-1"
                }),
                _cache[6] || (_cache[6] = _createTextVNode$4("检查登录 ", -1))
              ]),
              _: 1
            }, 8, ["loading"])
          ]),
          (qrcodeImage.value)
            ? (_openBlock$5(), _createElementBlock$5("div", _hoisted_4$1, [
                _createElementVNode$5("img", {
                  src: qrcodeImage.value,
                  alt: "115 登录二维码",
                  class: "qrcode-image"
                }, null, 8, _hoisted_5$1),
                _cache[7] || (_cache[7] = _createElementVNode$5("p", { class: "qrcode-hint" }, "用手机 115 APP 扫描上方二维码登录", -1))
              ]))
            : _createCommentVNode$3("", true),
          _withDirectives(_createVNode$5(_component_v_textarea, {
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
const AuthPanel = /*#__PURE__*/_export_sfc(_sfc_main$5, [['__scopeId',"data-v-ea378f22"]]);

const Dir115Picker_vue_vue_type_style_index_0_scoped_2b577c1a_lang = '';

const {createElementVNode:_createElementVNode$4,resolveComponent:_resolveComponent$4,createVNode:_createVNode$4,withCtx:_withCtx$3,toDisplayString:_toDisplayString$2,openBlock:_openBlock$4,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$2,renderList:_renderList$2,Fragment:_Fragment$2,createElementBlock:_createElementBlock$4,createTextVNode:_createTextVNode$3} = await importShared('vue');


const _hoisted_1$4 = { class: "breadcrumb-bar mb-4" };
const _hoisted_2$3 = { class: "breadcrumb-text" };

const {ref: ref$2,watch: watch$2} = await importShared('vue');


const _sfc_main$4 = {
  __name: 'Dir115Picker',
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

const loading = ref$2(false);
const refreshing = ref$2(false);
const items = ref$2([]);
const breadcrumbs = ref$2([{ ...ROOT_BREADCRUMB }]);

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

watch$2(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen) {
      loadDirectory('0', false);
    }
  }
);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$4("v-btn");
  const _component_v_card_title = _resolveComponent$4("v-card-title");
  const _component_v_divider = _resolveComponent$4("v-divider");
  const _component_v_progress_linear = _resolveComponent$4("v-progress-linear");
  const _component_v_list_item = _resolveComponent$4("v-list-item");
  const _component_v_icon = _resolveComponent$4("v-icon");
  const _component_v_list_item_title = _resolveComponent$4("v-list-item-title");
  const _component_v_list = _resolveComponent$4("v-list");
  const _component_v_card_text = _resolveComponent$4("v-card-text");
  const _component_v_spacer = _resolveComponent$4("v-spacer");
  const _component_v_card_actions = _resolveComponent$4("v-card-actions");
  const _component_v_card = _resolveComponent$4("v-card");
  const _component_v_dialog = _resolveComponent$4("v-dialog");

  return (_openBlock$4(), _createBlock$1(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": "600px",
    persistent: "",
    "onUpdate:modelValue": closeDialog
  }, {
    default: _withCtx$3(() => [
      _createVNode$4(_component_v_card, { class: "p115-path-selector" }, {
        default: _withCtx$3(() => [
          _createVNode$4(_component_v_card_title, { class: "d-flex align-center justify-space-between" }, {
            default: _withCtx$3(() => [
              _cache[0] || (_cache[0] = _createElementVNode$4("span", null, "选择 115 云盘目录", -1)),
              _createVNode$4(_component_v_btn, {
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
          _createVNode$4(_component_v_divider),
          _createVNode$4(_component_v_card_text, { class: "pa-4" }, {
            default: _withCtx$3(() => [
              _createElementVNode$4("div", _hoisted_1$4, [
                _createVNode$4(_component_v_btn, {
                  icon: "mdi-arrow-left",
                  size: "small",
                  variant: "text",
                  disabled: breadcrumbs.value.length <= 1 || loading.value,
                  onClick: goBack,
                  title: "返回上一级"
                }, null, 8, ["disabled"]),
                _createElementVNode$4("span", _hoisted_2$3, _toDisplayString$2(breadcrumbs.value.map(b => b.name).join(' / ')), 1)
              ]),
              (loading.value)
                ? (_openBlock$4(), _createBlock$1(_component_v_progress_linear, {
                    key: 0,
                    indeterminate: "",
                    class: "mb-3"
                  }))
                : (_openBlock$4(), _createBlock$1(_component_v_list, {
                    key: 1,
                    density: "compact",
                    class: "directory-list"
                  }, {
                    default: _withCtx$3(() => [
                      (items.value.length === 0)
                        ? (_openBlock$4(), _createBlock$1(_component_v_list_item, {
                            key: 0,
                            disabled: "",
                            class: "text-center text-grey"
                          }, {
                            default: _withCtx$3(() => [...(_cache[1] || (_cache[1] = [
                              _createElementVNode$4("span", null, "此目录为空", -1)
                            ]))]),
                            _: 1
                          }))
                        : _createCommentVNode$2("", true),
                      (_openBlock$4(true), _createElementBlock$4(_Fragment$2, null, _renderList$2(items.value, (item) => {
                        return (_openBlock$4(), _createBlock$1(_component_v_list_item, {
                          key: item.cid,
                          onClick: $event => (navigateToDirectory(item)),
                          class: "directory-item"
                        }, {
                          prepend: _withCtx$3(() => [
                            _createVNode$4(_component_v_icon, {
                              icon: "mdi-folder",
                              color: "#245B7A"
                            })
                          ]),
                          append: _withCtx$3(() => [
                            _createVNode$4(_component_v_icon, {
                              icon: "mdi-chevron-right",
                              size: "small",
                              color: "#999"
                            })
                          ]),
                          default: _withCtx$3(() => [
                            _createVNode$4(_component_v_list_item_title, null, {
                              default: _withCtx$3(() => [
                                _createTextVNode$3(_toDisplayString$2(item.name), 1)
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
          _createVNode$4(_component_v_divider),
          _createVNode$4(_component_v_card_actions, { class: "pa-4" }, {
            default: _withCtx$3(() => [
              _createVNode$4(_component_v_spacer),
              _createVNode$4(_component_v_btn, {
                variant: "plain",
                onClick: closeDialog,
                disabled: loading.value
              }, {
                default: _withCtx$3(() => [...(_cache[2] || (_cache[2] = [
                  _createTextVNode$3(" 取消 ", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$4(_component_v_btn, {
                color: "#245B7A",
                variant: "flat",
                onClick: selectCurrentDirectory,
                disabled: loading.value
              }, {
                default: _withCtx$3(() => [...(_cache[3] || (_cache[3] = [
                  _createTextVNode$3(" 选择当前目录 ", -1)
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
const Dir115Picker = /*#__PURE__*/_export_sfc(_sfc_main$4, [['__scopeId',"data-v-2b577c1a"]]);

const LocalDirPicker_vue_vue_type_style_index_0_scoped_4cb4eb3f_lang = '';

const {createElementVNode:_createElementVNode$3,resolveComponent:_resolveComponent$3,createVNode:_createVNode$3,withCtx:_withCtx$2,toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$2,withModifiers:_withModifiers,openBlock:_openBlock$3,createElementBlock:_createElementBlock$3,createCommentVNode:_createCommentVNode$1,createBlock:_createBlock,renderList:_renderList$1,Fragment:_Fragment$1} = await importShared('vue');


const _hoisted_1$3 = {
  key: 0,
  class: "breadcrumb-bar mb-4"
};

const {ref: ref$1,watch: watch$1} = await importShared('vue');


const _sfc_main$3 = {
  __name: 'LocalDirPicker',
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

const loading = ref$1(false);
const basePath = ref$1('');
const currentPath = ref$1('');
const items = ref$1([]);
const breadcrumbs = ref$1([]);

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
  const _component_v_icon = _resolveComponent$3("v-icon");
  const _component_v_card_title = _resolveComponent$3("v-card-title");
  const _component_v_divider = _resolveComponent$3("v-divider");
  const _component_v_breadcrumbs_item = _resolveComponent$3("v-breadcrumbs-item");
  const _component_v_breadcrumbs = _resolveComponent$3("v-breadcrumbs");
  const _component_v_progress_linear = _resolveComponent$3("v-progress-linear");
  const _component_v_list_item = _resolveComponent$3("v-list-item");
  const _component_v_list_item_title = _resolveComponent$3("v-list-item-title");
  const _component_v_list = _resolveComponent$3("v-list");
  const _component_v_card_text = _resolveComponent$3("v-card-text");
  const _component_v_spacer = _resolveComponent$3("v-spacer");
  const _component_v_btn = _resolveComponent$3("v-btn");
  const _component_v_card_actions = _resolveComponent$3("v-card-actions");
  const _component_v_card = _resolveComponent$3("v-card");
  const _component_v_dialog = _resolveComponent$3("v-dialog");

  return (_openBlock$3(), _createBlock(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": "600px",
    persistent: "",
    "onUpdate:modelValue": closeDialog
  }, {
    default: _withCtx$2(() => [
      _createVNode$3(_component_v_card, { class: "local-path-selector" }, {
        default: _withCtx$2(() => [
          _createVNode$3(_component_v_card_title, { class: "d-flex align-center justify-space-between" }, {
            default: _withCtx$2(() => [
              _cache[0] || (_cache[0] = _createElementVNode$3("span", null, "选择本地目录", -1)),
              _createVNode$3(_component_v_icon, { icon: "mdi-folder-outline" })
            ]),
            _: 1
          }),
          _createVNode$3(_component_v_divider),
          _createVNode$3(_component_v_card_text, { class: "pa-4" }, {
            default: _withCtx$2(() => [
              (breadcrumbs.value.length > 0)
                ? (_openBlock$3(), _createElementBlock$3("div", _hoisted_1$3, [
                    _createVNode$3(_component_v_breadcrumbs, {
                      items: breadcrumbs.value,
                      small: ""
                    }, {
                      item: _withCtx$2(({ item, index }) => [
                        _createVNode$3(_component_v_breadcrumbs_item, {
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
                : _createCommentVNode$1("", true),
              (loading.value)
                ? (_openBlock$3(), _createBlock(_component_v_progress_linear, {
                    key: 1,
                    indeterminate: "",
                    class: "mb-3"
                  }))
                : (_openBlock$3(), _createBlock(_component_v_list, {
                    key: 2,
                    density: "compact",
                    class: "directory-list"
                  }, {
                    default: _withCtx$2(() => [
                      (items.value.length === 0)
                        ? (_openBlock$3(), _createBlock(_component_v_list_item, {
                            key: 0,
                            disabled: "",
                            class: "text-center text-grey"
                          }, {
                            default: _withCtx$2(() => [...(_cache[1] || (_cache[1] = [
                              _createElementVNode$3("span", null, "此目录为空", -1)
                            ]))]),
                            _: 1
                          }))
                        : _createCommentVNode$1("", true),
                      (_openBlock$3(true), _createElementBlock$3(_Fragment$1, null, _renderList$1(items.value, (item) => {
                        return (_openBlock$3(), _createBlock(_component_v_list_item, {
                          key: item.path,
                          onClick: $event => (navigateToDirectory(item)),
                          class: "directory-item"
                        }, {
                          prepend: _withCtx$2(() => [
                            _createVNode$3(_component_v_icon, {
                              icon: "mdi-folder",
                              color: "#167A5B"
                            })
                          ]),
                          append: _withCtx$2(() => [
                            _createVNode$3(_component_v_icon, {
                              icon: "mdi-chevron-right",
                              size: "small",
                              color: "#999"
                            })
                          ]),
                          default: _withCtx$2(() => [
                            _createVNode$3(_component_v_list_item_title, null, {
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
          _createVNode$3(_component_v_divider),
          _createVNode$3(_component_v_card_actions, { class: "pa-4" }, {
            default: _withCtx$2(() => [
              _createVNode$3(_component_v_spacer),
              _createVNode$3(_component_v_btn, {
                variant: "plain",
                onClick: closeDialog,
                disabled: loading.value
              }, {
                default: _withCtx$2(() => [...(_cache[2] || (_cache[2] = [
                  _createTextVNode$2(" 取消 ", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$3(_component_v_btn, {
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
const LocalDirPicker = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-4cb4eb3f"]]);

const MappingEditor_vue_vue_type_style_index_0_scoped_1c89653a_lang = '';

const {createElementVNode:_createElementVNode$2,resolveComponent:_resolveComponent$2,createVNode:_createVNode$2,createTextVNode:_createTextVNode$1,withCtx:_withCtx$1,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1$2 = { class: "mapping-editor" };
const _hoisted_2$2 = { class: "mapping-editor__head" };
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

const {ref} = await importShared('vue');


const _sfc_main$2 = {
  __name: 'MappingEditor',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
  mappings: {
    type: Array,
    default: () => [],
  },
},
  emits: ['update:mappings', 'toast'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const dir115Open = ref(false);
const localOpen = ref(false);
const editingIndex = ref(null);

function makeId(index) {
  const rnd = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : `${index}-${Math.floor(performance.now())}`;
  return `m-${rnd}`
}

function addMapping() {
  emit('update:mappings', [
    ...props.mappings,
    { id: makeId(props.mappings.length), enabled: true, source_cid: '', source_path: '', target_dir: '' },
  ]);
}

function removeMapping(index) {
  emit('update:mappings', props.mappings.filter((_, idx) => idx !== index));
}

function patch(index, patchObj) {
  const next = props.mappings.map((m, idx) => (idx === index ? { ...m, ...patchObj } : m));
  emit('update:mappings', next);
}

function openDir115(index) {
  editingIndex.value = index;
  dir115Open.value = true;
}

function onDir115Selected(cid, name) {
  if (editingIndex.value !== null) {
    patch(editingIndex.value, { source_cid: String(cid), source_path: name });
  }
  dir115Open.value = false;
  editingIndex.value = null;
}

function openLocal(index) {
  editingIndex.value = index;
  localOpen.value = true;
}

function onLocalSelected(path) {
  if (editingIndex.value !== null) {
    patch(editingIndex.value, { target_dir: path });
  }
  localOpen.value = false;
  editingIndex.value = null;
}

function relayToast(msg, type) {
  emit('toast', msg, type);
}

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent$2("v-icon");
  const _component_v_btn = _resolveComponent$2("v-btn");
  const _component_v_switch = _resolveComponent$2("v-switch");
  const _component_v_text_field = _resolveComponent$2("v-text-field");

  return (_openBlock$2(), _createElementBlock$2("section", _hoisted_1$2, [
    _createElementVNode$2("div", _hoisted_2$2, [
      _cache[3] || (_cache[3] = _createElementVNode$2("div", null, [
        _createElementVNode$2("div", { class: "section-title" }, "路径映射"),
        _createElementVNode$2("div", { class: "section-subtitle" }, "115 源目录 → 本地 .strm 输出目录")
      ], -1)),
      _createVNode$2(_component_v_btn, {
        color: "#167A5B",
        variant: "flat",
        size: "small",
        onClick: addMapping
      }, {
        default: _withCtx$1(() => [
          _createVNode$2(_component_v_icon, {
            icon: "mdi-plus",
            class: "mr-1"
          }),
          _cache[2] || (_cache[2] = _createTextVNode$1("新增 ", -1))
        ]),
        _: 1
      })
    ]),
    (!__props.mappings.length)
      ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_3, "暂无映射"))
      : (_openBlock$2(), _createElementBlock$2("div", _hoisted_4, [
          (_openBlock$2(true), _createElementBlock$2(_Fragment, null, _renderList(__props.mappings, (mapping, index) => {
            return (_openBlock$2(), _createElementBlock$2("div", {
              key: mapping.id || index,
              class: "mapping-row"
            }, [
              _createVNode$2(_component_v_switch, {
                "model-value": mapping.enabled,
                color: "#167A5B",
                density: "compact",
                "hide-details": "",
                inset: "",
                "onUpdate:modelValue": $event => (patch(index, { enabled: $event }))
              }, null, 8, ["model-value", "onUpdate:modelValue"]),
              _createElementVNode$2("div", _hoisted_5, [
                _createVNode$2(_component_v_text_field, {
                  "model-value": mapping.source_path || '未选择',
                  label: "115 源目录",
                  variant: "outlined",
                  density: "compact",
                  "hide-details": "",
                  readonly: "",
                  "prepend-inner-icon": "mdi-cloud-outline"
                }, null, 8, ["model-value"]),
                _createVNode$2(_component_v_btn, {
                  icon: "mdi-cloud-search-outline",
                  size: "small",
                  variant: "text",
                  color: "#245B7A",
                  onClick: $event => (openDir115(index))
                }, null, 8, ["onClick"])
              ]),
              _createElementVNode$2("div", _hoisted_6, [
                _createVNode$2(_component_v_text_field, {
                  "model-value": mapping.target_dir || '未选择',
                  label: "本地输出目录",
                  variant: "outlined",
                  density: "compact",
                  "hide-details": "",
                  readonly: "",
                  "prepend-inner-icon": "mdi-folder-outline"
                }, null, 8, ["model-value"]),
                _createVNode$2(_component_v_btn, {
                  icon: "mdi-folder-open-outline",
                  size: "small",
                  variant: "text",
                  color: "#167A5B",
                  onClick: $event => (openLocal(index))
                }, null, 8, ["onClick"])
              ]),
              _createVNode$2(_component_v_btn, {
                icon: "mdi-delete-outline",
                size: "small",
                variant: "text",
                color: "#B42318",
                onClick: $event => (removeMapping(index))
              }, null, 8, ["onClick"])
            ]))
          }), 128))
        ])),
    _createVNode$2(Dir115Picker, {
      modelValue: dir115Open.value,
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((dir115Open).value = $event)),
      api: __props.api,
      onSelected: onDir115Selected,
      onToast: relayToast
    }, null, 8, ["modelValue", "api"]),
    _createVNode$2(LocalDirPicker, {
      modelValue: localOpen.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((localOpen).value = $event)),
      api: __props.api,
      onSelected: onLocalSelected,
      onToast: relayToast
    }, null, 8, ["modelValue", "api"])
  ]))
}
}

};
const MappingEditor = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-1c89653a"]]);

const SyncSettings_vue_vue_type_style_index_0_scoped_e4b19408_lang = '';

const {createElementVNode:_createElementVNode$1,resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1} = await importShared('vue');


const _hoisted_1$1 = { class: "sync-settings" };
const _hoisted_2$1 = { class: "switch-row" };


const _sfc_main$1 = {
  __name: 'SyncSettings',
  props: {
  config: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['update:config'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

function update(key, value) {
  emit('update:config', { ...props.config, [key]: value });
}

return (_ctx, _cache) => {
  const _component_v_text_field = _resolveComponent$1("v-text-field");
  const _component_v_switch = _resolveComponent$1("v-switch");

  return (_openBlock$1(), _createElementBlock$1("section", _hoisted_1$1, [
    _cache[5] || (_cache[5] = _createElementVNode$1("div", { class: "section-title" }, "同步设置", -1)),
    _createVNode$1(_component_v_text_field, {
      "model-value": __props.config.moviepilot_url,
      label: "MoviePilot 地址",
      variant: "outlined",
      density: "compact",
      "hide-details": "",
      placeholder: "http://10.10.10.3:3001",
      hint: "必须填媒体服务器能访问到的 MoviePilot 地址，否则 .strm 不可播",
      "persistent-hint": "",
      "prepend-inner-icon": "mdi-server-network",
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => (update('moviepilot_url', $event)))
    }, null, 8, ["model-value"]),
    _createVNode$1(_component_v_text_field, {
      "model-value": __props.config.app_id,
      label: "115 开放平台 APP ID",
      variant: "outlined",
      density: "compact",
      "hide-details": "",
      hint: "扫码登录所需；留空则回退 MoviePilot 全局 U115_APP_ID",
      "persistent-hint": "",
      "prepend-inner-icon": "mdi-identifier",
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => (update('app_id', $event)))
    }, null, 8, ["model-value"]),
    _createVNode$1(_component_v_text_field, {
      "model-value": __props.config.schedule_cron,
      label: "定时同步 Cron",
      variant: "outlined",
      density: "compact",
      "hide-details": "",
      placeholder: "0 4 * * *",
      hint: "留空则不定时；示例 0 4 * * * 表示每天 4 点",
      "persistent-hint": "",
      "prepend-inner-icon": "mdi-clock-outline",
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => (update('schedule_cron', $event)))
    }, null, 8, ["model-value"]),
    _createElementVNode$1("div", _hoisted_2$1, [
      _createVNode$1(_component_v_switch, {
        "model-value": __props.config.incremental,
        color: "#167A5B",
        density: "compact",
        "hide-details": "",
        inset: "",
        label: "增量同步（仅处理新增/变化文件）",
        "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => (update('incremental', $event)))
      }, null, 8, ["model-value"]),
      _createVNode$1(_component_v_switch, {
        "model-value": __props.config.sync_metadata,
        color: "#167A5B",
        density: "compact",
        "hide-details": "",
        inset: "",
        label: "刮削文件同步（nfo/海报/字幕）",
        "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => (update('sync_metadata', $event)))
      }, null, 8, ["model-value"])
    ])
  ]))
}
}

};
const SyncSettings = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-e4b19408"]]);

const Config_vue_vue_type_style_index_0_scoped_551cc525_lang = '';

const {createVNode:_createVNode,resolveComponent:_resolveComponent,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "p115-config" };
const _hoisted_2 = { class: "config-actions" };

const {reactive,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
  saving: {
    type: Boolean,
    default: false,
  },
},
  emits: ['save', 'switch', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const snackbar = reactive({ show: false, text: '', color: 'info' });

const config = reactive({
  auth_mode: 'qrcode',
  cookie: '',
  app_id: '',
  moviepilot_url: '',
  schedule_cron: '',
  incremental: true,
  sync_metadata: false,
  mappings: [],
  ...(props.initialConfig || {}),
});

watch(
  () => props.initialConfig,
  (val) => {
    if (val) Object.assign(config, val);
  },
);

function updateConfig(next) {
  Object.assign(config, next);
}

function updateMappings(next) {
  config.mappings = next;
}

function toast(message, type = 'info') {
  snackbar.text = message;
  snackbar.color = type === 'error' ? 'error' : type === 'success' ? 'success' : 'info';
  snackbar.show = true;
}

function save() {
  emit('save', { ...config, mappings: [...config.mappings] });
}

return (_ctx, _cache) => {
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(AuthPanel, {
      api: __props.api,
      config: config,
      "onUpdate:config": updateConfig,
      onToast: toast
    }, null, 8, ["api", "config"]),
    _createVNode(_component_v_divider, { class: "my-2" }),
    _createVNode(SyncSettings, {
      config: config,
      "onUpdate:config": updateConfig
    }, null, 8, ["config"]),
    _createVNode(_component_v_divider, { class: "my-2" }),
    _createVNode(MappingEditor, {
      api: __props.api,
      mappings: config.mappings,
      "onUpdate:mappings": updateMappings,
      onToast: toast
    }, null, 8, ["api", "mappings"]),
    _createElementVNode("div", _hoisted_2, [
      _createVNode(_component_v_btn, {
        variant: "text",
        onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_icon, {
            icon: "mdi-view-dashboard-outline",
            class: "mr-1"
          }),
          _cache[3] || (_cache[3] = _createTextVNode("数据页 ", -1))
        ]),
        _: 1
      }),
      _createVNode(_component_v_spacer),
      _createVNode(_component_v_btn, {
        variant: "text",
        onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
      }, {
        default: _withCtx(() => [...(_cache[4] || (_cache[4] = [
          _createTextVNode("取消", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_v_btn, {
        color: "#167A5B",
        variant: "flat",
        loading: __props.saving,
        onClick: save
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_icon, {
            icon: "mdi-content-save",
            class: "mr-1"
          }),
          _cache[5] || (_cache[5] = _createTextVNode("保存 ", -1))
        ]),
        _: 1
      }, 8, ["loading"])
    ]),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((snackbar.show) = $event)),
      color: snackbar.color,
      timeout: "3000",
      location: "top"
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
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-551cc525"]]);

export { Config as default };
