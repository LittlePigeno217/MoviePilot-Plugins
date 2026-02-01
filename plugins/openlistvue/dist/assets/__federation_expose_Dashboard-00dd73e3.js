import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const Dashboard_vue_vue_type_style_index_0_scoped_b39a0cf9_lang = '';

const {defineComponent,ref} = await importShared('vue');


const _sfc_main = defineComponent({
  name: 'Dashboard',
  props: {
    config: {
      type: Object,
      default: () => ({})
    },
    allowRefresh: {
      type: Boolean,
      default: true
    }
  },
  setup() {
    // 仪表板状态
    const isHovering = ref(false);

    return {
      isHovering
    }
  }
});

const {toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,normalizeClass:_normalizeClass,createStaticVNode:_createStaticVNode} = await importShared('vue');


const _hoisted_1 = { class: "dashboard-widget" };
const _hoisted_2 = { class: "widget-header" };
const _hoisted_3 = {
  key: 0,
  class: "widget-actions"
};
const _hoisted_4 = { class: "widget-content" };
const _hoisted_5 = { class: "status-item" };
const _hoisted_6 = { class: "status-item" };
const _hoisted_7 = { class: "status-value" };
const _hoisted_8 = { class: "status-item" };
const _hoisted_9 = { class: "status-value truncate" };
const _hoisted_10 = { class: "widget-footer" };
const _hoisted_11 = { class: "widget-version" };

function _sfc_render(_ctx, _cache, $props, $setup, $data, $options) {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", {
      class: "widget-card",
      onMouseenter: _cache[0] || (_cache[0] = $event => (_ctx.isHovering = true)),
      onMouseleave: _cache[1] || (_cache[1] = $event => (_ctx.isHovering = false))
    }, [
      _createElementVNode("div", _hoisted_2, [
        _createElementVNode("h3", null, _toDisplayString(_ctx.config.title || 'OpenList管理Vue'), 1),
        (_ctx.isHovering)
          ? (_openBlock(), _createElementBlock("div", _hoisted_3, [...(_cache[2] || (_cache[2] = [
              _createStaticVNode("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"16\" height=\"16\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" class=\"cursor-move\" data-v-b39a0cf9><polyline points=\"5 9 2 12 5 15\" data-v-b39a0cf9></polyline><polyline points=\"9 5 12 2 15 5\" data-v-b39a0cf9></polyline><polyline points=\"15 19 12 22 9 19\" data-v-b39a0cf9></polyline><polyline points=\"19 9 22 12 19 15\" data-v-b39a0cf9></polyline><line x1=\"2\" y1=\"12\" x2=\"22\" y2=\"12\" data-v-b39a0cf9></line><line x1=\"12\" y1=\"2\" x2=\"12\" y2=\"22\" data-v-b39a0cf9></line></svg>", 1)
            ]))]))
          : _createCommentVNode("", true)
      ]),
      _createElementVNode("div", _hoisted_4, [
        _createElementVNode("div", _hoisted_5, [
          _cache[3] || (_cache[3] = _createElementVNode("div", { class: "status-label" }, "插件状态", -1)),
          _createElementVNode("div", {
            class: _normalizeClass(["status-value", _ctx.config.enabled ? 'status-enabled' : 'status-disabled'])
          }, _toDisplayString(_ctx.config.enabled ? '已启用' : '已禁用'), 3)
        ]),
        _createElementVNode("div", _hoisted_6, [
          _cache[4] || (_cache[4] = _createElementVNode("div", { class: "status-label" }, "执行周期", -1)),
          _createElementVNode("div", _hoisted_7, _toDisplayString(_ctx.config.cron || '未设置'), 1)
        ]),
        _createElementVNode("div", _hoisted_8, [
          _cache[5] || (_cache[5] = _createElementVNode("div", { class: "status-label" }, "OpenList地址", -1)),
          _createElementVNode("div", _hoisted_9, _toDisplayString(_ctx.config.openlist_url || '未设置'), 1)
        ])
      ]),
      _createElementVNode("div", _hoisted_10, [
        _createElementVNode("div", _hoisted_11, "版本 " + _toDisplayString(_ctx.config.version || '1.2'), 1),
        _cache[6] || (_cache[6] = _createElementVNode("div", { class: "widget-author" }, "LittlePigeno", -1))
      ])
    ], 32)
  ]))
}
const Dashboard = /*#__PURE__*/_export_sfc(_sfc_main, [['render',_sfc_render],['__scopeId',"data-v-b39a0cf9"]]);

export { Dashboard as default };
