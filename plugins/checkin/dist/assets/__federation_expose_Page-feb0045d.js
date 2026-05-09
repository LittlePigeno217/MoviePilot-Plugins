import { importShared } from './__federation_fn_import-054b33c3.js';
import { s as statusColor, g as getSiteDisplayMeta, p as pluginRequest } from './index-7b3b5f0c.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const Page_vue_vue_type_style_index_0_scoped_1e31cd93_lang = '';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,unref:_unref,createBlock:_createBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');


const _hoisted_1 = { class: "flzt-page" };
const _hoisted_2 = { class: "flzt-page__hero" };
const _hoisted_3 = { class: "overview-grid" };
const _hoisted_4 = { class: "overview-item" };
const _hoisted_5 = { class: "overview-item" };
const _hoisted_6 = { class: "overview-item" };
const _hoisted_7 = { class: "overview-item__value" };
const _hoisted_8 = { class: "overview-item" };
const _hoisted_9 = { class: "overview-item__value" };
const _hoisted_10 = { class: "overview-item" };
const _hoisted_11 = { class: "overview-item" };
const _hoisted_12 = { class: "overview-item__value" };
const _hoisted_13 = { class: "overview-item" };
const _hoisted_14 = { class: "overview-item__value" };
const _hoisted_15 = { class: "overview-item" };
const _hoisted_16 = { class: "overview-item__value" };
const _hoisted_17 = { class: "site-item__chips" };
const _hoisted_18 = {
  key: 0,
  class: "history-list"
};
const _hoisted_19 = { class: "history-entry__header" };
const _hoisted_20 = { class: "history-entry__time" };
const _hoisted_21 = { class: "history-entry__message" };
const _hoisted_22 = { class: "history-entry__chips" };
const _hoisted_23 = { class: "history-message" };
const _hoisted_24 = {
  key: 1,
  class: "text-center text-medium-emphasis py-6"
};

const {computed,onMounted,reactive,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: [Function, Object], default: null },
  initialConfig: { type: Object, default: () => ({}) },
},
  emits: ['switch', 'close', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = ref(false);
const running = ref(false);
const testing = ref(false);
const clearing = ref(false);
const snackbar = reactive({ show: false, text: '', type: 'success' });
const status = ref({
  enabled: false,
  configured: false,
  cron: '',
  enabled_site_count: 0,
  configured_site_count: 0,
  last_status: '未执行',
  last_run: '-',
  sites: [],
  history: [],
  history_count: 0,
  next_run_time: '未配置定时任务',
  task_status: '未启用',
  last_result: null,
});

function showMessage(text, type = 'success') {
  snackbar.text = text;
  snackbar.type = type;
  snackbar.show = true;
}

async function loadStatus(showSuccess = false) {
  loading.value = true;
  try {
    const result = await pluginRequest(props.api, '/status');
    if (!result?.success) {
      throw new Error(result?.message || '获取状态失败')
    }
    status.value = result.data || status.value;
    if (showSuccess) {
      showMessage('状态已刷新');
    }
  } catch (error) {
    showMessage(error?.message || '获取状态失败', 'error');
  } finally {
    loading.value = false;
  }
}

async function runCheckin() {
  running.value = true;
  try {
    const result = await pluginRequest(props.api, '/run', { method: 'POST', body: {} });
    if (!result?.success) {
      throw new Error(result?.message || '执行失败')
    }
    showMessage(result?.message || '执行成功');
    await loadStatus();
    emit('action');
  } catch (error) {
    showMessage(error?.message || '执行失败', 'error');
  } finally {
    running.value = false;
  }
}

async function testLogin() {
  testing.value = true;
  try {
    const result = await pluginRequest(props.api, '/test-login', { method: 'POST', body: {} });
    if (!result?.success) {
      throw new Error(result?.message || '测试失败')
    }
    showMessage(result?.message || '登录测试成功');
  } catch (error) {
    showMessage(error?.message || '登录测试失败', 'error');
  } finally {
    testing.value = false;
  }
}

async function clearHistory() {
  clearing.value = true;
  try {
    const result = await pluginRequest(props.api, '/history/clear', { method: 'POST', body: {} });
    if (!result?.success) {
      throw new Error(result?.message || '清空失败')
    }
    showMessage(result?.message || '已清空历史');
    await loadStatus();
  } catch (error) {
    showMessage(error?.message || '清空历史失败', 'error');
  } finally {
    clearing.value = false;
  }
}

const statusChipColor = computed(() => statusColor(status.value.last_status));
const siteSummary = computed(() => (status.value.sites || []).filter(site => site.enabled));
const historyEntries = computed(() => status.value.history || []);

onMounted(() => {
  loadStatus();
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_group = _resolveComponent("v-btn-group");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_divider = _resolveComponent("v-divider");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");
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
      _cache[6] || (_cache[6] = _createElementVNode("div", null, [
        _createElementVNode("div", { class: "flzt-page__title" }, "自用签到工具"),
        _createElementVNode("div", { class: "flzt-page__subtitle" }, "查看状态并执行签到")
      ], -1)),
      _createVNode(_component_v_btn_group, {
        variant: "tonal",
        density: "comfortable"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_btn, {
            color: "primary",
            loading: loading.value,
            onClick: _cache[0] || (_cache[0] = $event => (loadStatus(true)))
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                icon: "mdi-refresh",
                class: "mr-1"
              }),
              _cache[4] || (_cache[4] = _createTextVNode("刷新 ", -1))
            ]),
            _: 1
          }, 8, ["loading"]),
          _createVNode(_component_v_btn, {
            color: "primary",
            onClick: _cache[1] || (_cache[1] = $event => (emit('switch')))
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, {
                icon: "mdi-cog-outline",
                class: "mr-1"
              }),
              _cache[5] || (_cache[5] = _createTextVNode("配置 ", -1))
            ]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            color: "primary",
            onClick: _cache[2] || (_cache[2] = $event => (emit('close')))
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, { icon: "mdi-close" })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
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
                  default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
                    _createTextVNode("概览", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_3, [
                      _createElementVNode("div", _hoisted_4, [
                        _cache[8] || (_cache[8] = _createElementVNode("div", { class: "overview-item__label" }, "状态", -1)),
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
                      _createElementVNode("div", _hoisted_5, [
                        _cache[9] || (_cache[9] = _createElementVNode("div", { class: "overview-item__label" }, "配置", -1)),
                        _createVNode(_component_v_chip, {
                          color: status.value.configured ? 'success' : 'warning',
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(status.value.configured ? '已完成' : '未完成'), 1)
                          ]),
                          _: 1
                        }, 8, ["color"])
                      ]),
                      _createElementVNode("div", _hoisted_6, [
                        _cache[10] || (_cache[10] = _createElementVNode("div", { class: "overview-item__label" }, "启用站点", -1)),
                        _createElementVNode("div", _hoisted_7, _toDisplayString(status.value.enabled_site_count || 0) + " 个", 1)
                      ]),
                      _createElementVNode("div", _hoisted_8, [
                        _cache[11] || (_cache[11] = _createElementVNode("div", { class: "overview-item__label" }, "已配置站点", -1)),
                        _createElementVNode("div", _hoisted_9, _toDisplayString(status.value.configured_site_count || 0) + " 个", 1)
                      ]),
                      _createElementVNode("div", _hoisted_10, [
                        _cache[12] || (_cache[12] = _createElementVNode("div", { class: "overview-item__label" }, "最近结果", -1)),
                        _createVNode(_component_v_chip, {
                          color: statusChipColor.value,
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(status.value.last_status || '-'), 1)
                          ]),
                          _: 1
                        }, 8, ["color"])
                      ]),
                      _createElementVNode("div", _hoisted_11, [
                        _cache[13] || (_cache[13] = _createElementVNode("div", { class: "overview-item__label" }, "最近执行", -1)),
                        _createElementVNode("div", _hoisted_12, _toDisplayString(status.value.last_run || '-'), 1)
                      ]),
                      _createElementVNode("div", _hoisted_13, [
                        _cache[14] || (_cache[14] = _createElementVNode("div", { class: "overview-item__label" }, "下次执行", -1)),
                        _createElementVNode("div", _hoisted_14, _toDisplayString(status.value.next_run_time || '-'), 1)
                      ]),
                      _createElementVNode("div", _hoisted_15, [
                        _cache[15] || (_cache[15] = _createElementVNode("div", { class: "overview-item__label" }, "Cron", -1)),
                        _createElementVNode("div", _hoisted_16, _toDisplayString(status.value.cron || '-'), 1)
                      ])
                    ])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_divider),
                _createVNode(_component_v_card_actions, { class: "flex-wrap ga-2 pa-4" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_btn, {
                      color: "success",
                      loading: running.value,
                      onClick: runCheckin
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_icon, {
                          icon: "mdi-play-circle-outline",
                          class: "mr-1"
                        }),
                        _cache[16] || (_cache[16] = _createTextVNode("立即签到 ", -1))
                      ]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      color: "info",
                      variant: "tonal",
                      loading: testing.value,
                      onClick: testLogin
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_icon, {
                          icon: "mdi-shield-check-outline",
                          class: "mr-1"
                        }),
                        _cache[17] || (_cache[17] = _createTextVNode("测试登录 ", -1))
                      ]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      color: "error",
                      variant: "tonal",
                      loading: clearing.value,
                      onClick: clearHistory
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_icon, {
                          icon: "mdi-delete-sweep-outline",
                          class: "mr-1"
                        }),
                        _cache[18] || (_cache[18] = _createTextVNode("清空历史 ", -1))
                      ]),
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
                  default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                    _createTextVNode("已启用站点", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_list, {
                      lines: "two",
                      density: "comfortable"
                    }, {
                      default: _withCtx(() => [
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(siteSummary.value, (site) => {
                          return (_openBlock(), _createBlock(_component_v_list_item, {
                            key: site.key
                          }, {
                            prepend: _withCtx(() => [
                              _createVNode(_component_v_icon, {
                                icon: _unref(getSiteDisplayMeta)(site.key).icon
                              }, null, 8, ["icon"])
                            ]),
                            append: _withCtx(() => [
                              _createElementVNode("div", _hoisted_17, [
                                _createVNode(_component_v_chip, {
                                  size: "small",
                                  color: site.use_proxy ? 'info' : 'default',
                                  variant: "tonal"
                                }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(site.use_proxy ? '代理' : '直连'), 1)
                                  ]),
                                  _: 2
                                }, 1032, ["color"]),
                                _createVNode(_component_v_chip, {
                                  size: "small",
                                  color: site.configured ? 'success' : 'warning',
                                  variant: "tonal"
                                }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(site.configured ? '已就绪' : '待配置'), 1)
                                  ]),
                                  _: 2
                                }, 1032, ["color"])
                              ])
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
                        (!siteSummary.value.length)
                          ? (_openBlock(), _createBlock(_component_v_list_item, { key: 0 }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_list_item_title, null, {
                                  default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                                    _createTextVNode("暂无已启用站点", -1)
                                  ]))]),
                                  _: 1
                                }),
                                _createVNode(_component_v_list_item_subtitle, null, {
                                  default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
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
                _createVNode(_component_v_card_title, { class: "d-flex align-center justify-space-between" }, {
                  default: _withCtx(() => [
                    _cache[22] || (_cache[22] = _createElementVNode("span", null, "签到历史", -1)),
                    _createVNode(_component_v_chip, {
                      color: "primary",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(status.value.history_count || 0) + " 次", 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    (historyEntries.value.length)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_18, [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(historyEntries.value, (entry, index) => {
                            return (_openBlock(), _createBlock(_component_v_card, {
                              key: `${entry.time}-${index}`,
                              variant: "tonal",
                              class: "history-entry"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_card_text, null, {
                                  default: _withCtx(() => [
                                    _createElementVNode("div", _hoisted_19, [
                                      _createElementVNode("div", null, [
                                        _createElementVNode("div", _hoisted_20, _toDisplayString(entry.time || '-'), 1),
                                        _createElementVNode("div", _hoisted_21, _toDisplayString(entry.message || '-'), 1)
                                      ]),
                                      _createElementVNode("div", _hoisted_22, [
                                        _createVNode(_component_v_chip, {
                                          size: "small",
                                          color: _unref(statusColor)(entry.status),
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx(() => [
                                            _createTextVNode(_toDisplayString(entry.status || '-'), 1)
                                          ]),
                                          _: 2
                                        }, 1032, ["color"]),
                                        _createVNode(_component_v_chip, {
                                          size: "small",
                                          color: "success",
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx(() => [
                                            _createTextVNode(" 成功 " + _toDisplayString(entry.success_count || 0), 1)
                                          ]),
                                          _: 2
                                        }, 1024),
                                        _createVNode(_component_v_chip, {
                                          size: "small",
                                          color: "error",
                                          variant: "tonal"
                                        }, {
                                          default: _withCtx(() => [
                                            _createTextVNode(" 失败 " + _toDisplayString(entry.failure_count || 0), 1)
                                          ]),
                                          _: 2
                                        }, 1024)
                                      ])
                                    ]),
                                    _createVNode(_component_v_table, {
                                      density: "comfortable",
                                      class: "history-entry__table"
                                    }, {
                                      default: _withCtx(() => [
                                        _cache[23] || (_cache[23] = _createElementVNode("thead", null, [
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
                                              _createElementVNode("td", _hoisted_23, _toDisplayString(detail.message || '-'), 1)
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
                      : (_openBlock(), _createElementBlock("div", _hoisted_24, "暂无签到历史"))
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
      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((snackbar.show) = $event)),
      color: snackbar.type,
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-1e31cd93"]]);

export { Page as default };
