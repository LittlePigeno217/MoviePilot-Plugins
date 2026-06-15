import { importShared } from './__federation_fn_import-054b33c3.js';
import { s as statusColor, S as SITE_META, p as pluginGet, a as pluginPost } from './plugin-c8525d6a.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,unref:_unref,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "checkin-page pa-4" };
const _hoisted_2 = { class: "d-flex align-center justify-space-between mb-4" };
const _hoisted_3 = { class: "d-flex ga-2" };
const _hoisted_4 = { class: "d-flex flex-column ga-3" };
const _hoisted_5 = { class: "d-flex justify-space-between" };
const _hoisted_6 = { class: "d-flex justify-space-between" };
const _hoisted_7 = { class: "d-flex justify-space-between" };
const _hoisted_8 = { class: "d-flex justify-space-between" };
const _hoisted_9 = { class: "d-flex justify-space-between" };
const _hoisted_10 = { class: "d-flex justify-space-between" };
const _hoisted_11 = { class: "d-flex justify-space-between" };
const _hoisted_12 = {
  key: 0,
  class: "d-flex flex-column ga-3"
};
const _hoisted_13 = { class: "d-flex flex-wrap align-center justify-space-between ga-2 mb-3" };
const _hoisted_14 = { class: "text-subtitle-2" };
const _hoisted_15 = { class: "text-body-2 text-medium-emphasis" };
const _hoisted_16 = {
  key: 1,
  class: "text-medium-emphasis py-6 text-center"
};

const {computed,onMounted,reactive,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
  show_switch: {
    type: Boolean,
    default: true,
  },
},
  emits: ['action', 'switch', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = ref(false);
const running = ref(false);
const testing = ref(false);
const clearing = ref(false);
const snackbar = reactive({ show: false, text: '', color: 'info' });
const status = ref({
  sites: [],
  history: [],
});

const enabledSites = computed(() => status.value.sites?.filter(site => site.enabled) || []);
const history = computed(() => status.value.history || []);

function notify(text, color = 'info') {
  snackbar.text = text;
  snackbar.color = color;
  snackbar.show = true;
}

async function refresh() {
  loading.value = true;
  try {
    status.value = await pluginGet(props.api, '/status');
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
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_list_item_title = _resolveComponent("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_list = _resolveComponent("v-list");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_table = _resolveComponent("v-table");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_snackbar = _resolveComponent("v-snackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[3] || (_cache[3] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "text-h6" }, "自用签到工具"),
        _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "站点签到状态、历史记录和手动执行。")
      ], -1)),
      _createElementVNode("div", _hoisted_3, [
        _createVNode(_component_v_btn, {
          icon: "mdi-refresh",
          variant: "tonal",
          loading: loading.value,
          onClick: refresh
        }, null, 8, ["loading"]),
        (__props.show_switch)
          ? (_openBlock(), _createBlock(_component_v_btn, {
              key: 0,
              icon: "mdi-cog-outline",
              variant: "tonal",
              onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
            }))
          : _createCommentVNode("", true),
        _createVNode(_component_v_btn, {
          icon: "mdi-close",
          variant: "text",
          onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
        })
      ])
    ]),
    _createVNode(_component_v_row, null, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, {
          cols: "12",
          lg: "4"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              variant: "outlined",
              class: "mb-4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, null, {
                  default: _withCtx(() => [...(_cache[4] || (_cache[4] = [
                    _createTextVNode("概览", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_4, [
                      _createElementVNode("div", _hoisted_5, [
                        _cache[5] || (_cache[5] = _createElementVNode("span", { class: "text-medium-emphasis" }, "状态", -1)),
                        _createVNode(_component_v_chip, {
                          color: status.value.enabled ? 'success' : 'grey',
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(status.value.enabled ? '已启用' : '未启用'), 1)
                          ]),
                          _: 1
                        }, 8, ["color"])
                      ]),
                      _createElementVNode("div", _hoisted_6, [
                        _cache[6] || (_cache[6] = _createElementVNode("span", { class: "text-medium-emphasis" }, "配置", -1)),
                        _createVNode(_component_v_chip, {
                          color: status.value.configured ? 'success' : 'warning',
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(status.value.configured ? '已完成' : '待完善'), 1)
                          ]),
                          _: 1
                        }, 8, ["color"])
                      ]),
                      _createElementVNode("div", _hoisted_7, [
                        _cache[7] || (_cache[7] = _createElementVNode("span", { class: "text-medium-emphasis" }, "启用站点", -1)),
                        _createElementVNode("span", null, _toDisplayString(status.value.enabled_site_count || 0), 1)
                      ]),
                      _createElementVNode("div", _hoisted_8, [
                        _cache[8] || (_cache[8] = _createElementVNode("span", { class: "text-medium-emphasis" }, "已配置站点", -1)),
                        _createElementVNode("span", null, _toDisplayString(status.value.configured_site_count || 0), 1)
                      ]),
                      _createElementVNode("div", _hoisted_9, [
                        _cache[9] || (_cache[9] = _createElementVNode("span", { class: "text-medium-emphasis" }, "最近结果", -1)),
                        _createVNode(_component_v_chip, {
                          color: _unref(statusColor)(status.value.last_status),
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(status.value.last_status || '-'), 1)
                          ]),
                          _: 1
                        }, 8, ["color"])
                      ]),
                      _createElementVNode("div", _hoisted_10, [
                        _cache[10] || (_cache[10] = _createElementVNode("span", { class: "text-medium-emphasis" }, "最近执行", -1)),
                        _createElementVNode("span", null, _toDisplayString(status.value.last_run || '-'), 1)
                      ]),
                      _createElementVNode("div", _hoisted_11, [
                        _cache[11] || (_cache[11] = _createElementVNode("span", { class: "text-medium-emphasis" }, "下次执行", -1)),
                        _createElementVNode("span", null, _toDisplayString(status.value.next_run_time || '-'), 1)
                      ])
                    ])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_actions, { class: "flex-wrap ga-2" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_btn, {
                      color: "success",
                      "prepend-icon": "mdi-play-circle-outline",
                      loading: running.value,
                      onClick: runCheckin
                    }, {
                      default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
                        _createTextVNode(" 立即签到 ", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      color: "info",
                      variant: "tonal",
                      "prepend-icon": "mdi-shield-check-outline",
                      loading: testing.value,
                      onClick: testLogin
                    }, {
                      default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
                        _createTextVNode(" 测试登录 ", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      color: "error",
                      variant: "tonal",
                      "prepend-icon": "mdi-delete-sweep-outline",
                      loading: clearing.value,
                      onClick: clearHistory
                    }, {
                      default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
                        _createTextVNode(" 清空历史 ", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_v_card, { variant: "outlined" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, null, {
                  default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
                    _createTextVNode("启用站点", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_list, {
                  lines: "two",
                  density: "comfortable"
                }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(enabledSites.value, (site) => {
                      return (_openBlock(), _createBlock(_component_v_list_item, {
                        key: site.key
                      }, {
                        prepend: _withCtx(() => [
                          _createVNode(_component_v_icon, {
                            icon: _unref(SITE_META)[site.key]?.icon || 'mdi-web'
                          }, null, 8, ["icon"])
                        ]),
                        append: _withCtx(() => [
                          _createVNode(_component_v_chip, {
                            size: "small",
                            color: site.configured ? 'success' : 'warning',
                            variant: "tonal"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(site.configured ? '已配置' : '待配置'), 1)
                            ]),
                            _: 2
                          }, 1032, ["color"])
                        ]),
                        default: _withCtx(() => [
                          _createVNode(_component_v_list_item_title, null, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(site.name), 1)
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode(_component_v_list_item_subtitle, null, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(site.account || '-') + " / " + _toDisplayString(site.last_status || '未执行'), 1)
                            ]),
                            _: 2
                          }, 1024)
                        ]),
                        _: 2
                      }, 1024))
                    }), 128)),
                    (!enabledSites.value.length)
                      ? (_openBlock(), _createBlock(_component_v_list_item, { key: 0 }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_list_item_title, null, {
                              default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                                _createTextVNode("暂无启用站点", -1)
                              ]))]),
                              _: 1
                            }),
                            _createVNode(_component_v_list_item_subtitle, null, {
                              default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                                _createTextVNode("请先到配置页启用站点", -1)
                              ]))]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true)
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_v_col, {
          cols: "12",
          lg: "8"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, { variant: "outlined" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "d-flex justify-space-between" }, {
                  default: _withCtx(() => [
                    _cache[18] || (_cache[18] = _createElementVNode("span", null, "签到历史", -1)),
                    _createVNode(_component_v_chip, {
                      color: "primary",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(status.value.history_count || history.value.length) + " 次", 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    (history.value.length)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_12, [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(history.value, (entry, index) => {
                            return (_openBlock(), _createBlock(_component_v_card, {
                              key: `${entry.time}-${index}`,
                              variant: "tonal"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_card_text, null, {
                                  default: _withCtx(() => [
                                    _createElementVNode("div", _hoisted_13, [
                                      _createElementVNode("div", null, [
                                        _createElementVNode("div", _hoisted_14, _toDisplayString(entry.time || '-'), 1),
                                        _createElementVNode("div", _hoisted_15, _toDisplayString(entry.message || '-'), 1)
                                      ]),
                                      _createVNode(_component_v_chip, {
                                        color: _unref(statusColor)(entry.status),
                                        variant: "tonal"
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(entry.status || '-'), 1)
                                        ]),
                                        _: 2
                                      }, 1032, ["color"])
                                    ]),
                                    _createVNode(_component_v_table, { density: "compact" }, {
                                      default: _withCtx(() => [
                                        _cache[19] || (_cache[19] = _createElementVNode("thead", null, [
                                          _createElementVNode("tr", null, [
                                            _createElementVNode("th", null, "站点"),
                                            _createElementVNode("th", null, "状态"),
                                            _createElementVNode("th", null, "账号"),
                                            _createElementVNode("th", null, "消息")
                                          ])
                                        ], -1)),
                                        _createElementVNode("tbody", null, [
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(entry.details || [], (detail, detailIndex) => {
                                            return (_openBlock(), _createElementBlock("tr", {
                                              key: `${entry.time}-${detail.site}-${detailIndex}`
                                            }, [
                                              _createElementVNode("td", null, _toDisplayString(detail.site_name || detail.site || '-'), 1),
                                              _createElementVNode("td", null, [
                                                _createVNode(_component_v_chip, {
                                                  size: "small",
                                                  color: _unref(statusColor)(detail.status),
                                                  variant: "tonal"
                                                }, {
                                                  default: _withCtx(() => [
                                                    _createTextVNode(_toDisplayString(detail.status || '-'), 1)
                                                  ]),
                                                  _: 2
                                                }, 1032, ["color"])
                                              ]),
                                              _createElementVNode("td", null, _toDisplayString(detail.account || '-'), 1),
                                              _createElementVNode("td", null, _toDisplayString(detail.message || '-'), 1)
                                            ]))
                                          }), 128))
                                        ])
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024)
                              ]),
                              _: 2
                            }, 1024))
                          }), 128))
                        ]))
                      : (_openBlock(), _createElementBlock("div", _hoisted_16, "暂无签到历史"))
                  ]),
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
    }),
    _createVNode(_component_v_snackbar, {
      modelValue: snackbar.show,
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((snackbar.show) = $event)),
      color: snackbar.color,
      timeout: "3000"
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

export { _sfc_main as default };
