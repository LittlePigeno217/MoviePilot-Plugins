/**
 * 独立联调用的宿主替身。MoviePilot 真正的宿主会注入自己的 Vuetify 主题，
 * 这里按 MoviePilot v2 的主题值复刻一份浅色 / 深色，用来验证插件是否真的跟随主题。
 */
import { createApp, h, ref } from 'vue'
import { createVuetify, useTheme } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import Config from './components/Config.vue'
import Page from './components/Page.vue'

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'mpLight',
    themes: {
      mpLight: {
        dark: false,
        colors: {
          primary: '#8D51F9',
          background: '#F4F5FA',
          surface: '#FFFFFF',
          'on-surface': '#3A3541',
          'on-primary': '#FFFFFF',
          success: '#56CA00',
          error: '#FF4C51',
          warning: '#FFB400',
        },
        variables: { 'border-color': '#3A3541', 'border-opacity': 0.12, 'medium-emphasis-opacity': 0.68 },
      },
      mpDark: {
        dark: true,
        colors: {
          primary: '#6E66ED',
          background: '#0E1116',
          surface: '#14161F',
          'on-surface': '#E7E3FC',
          'on-primary': '#FFFFFF',
          success: '#56CA00',
          error: '#FF4C51',
          warning: '#FFB400',
        },
        variables: { 'border-color': '#E7E3FC', 'border-opacity': 0.12, 'medium-emphasis-opacity': 0.68 },
      },
    },
  },
})

const Harness = {
  setup() {
    const theme = useTheme()
    const view = ref('config')
    const toggle = () => {
      const next = theme.global.name.value === 'mpLight' ? 'mpDark' : 'mpLight'
      if (typeof theme.change === 'function') theme.change(next)
      else theme.global.name.value = next
    }
    return () =>
      h('div', { style: 'min-height:100vh;background:rgb(var(--v-theme-background));padding:24px' }, [
        h('div', { style: 'display:flex;gap:8px;margin-bottom:16px' }, [
          h(components.VBtn, { size: 'small', onClick: toggle }, () => `主题：${theme.global.name.value}`),
          h(
            components.VBtn,
            { size: 'small', onClick: () => (view.value = view.value === 'config' ? 'page' : 'config') },
            () => `视图：${view.value}`,
          ),
        ]),
        h(
          components.VCard,
          { style: 'max-width:58rem;margin:auto;overflow:hidden' },
          () => [h(view.value === 'config' ? Config : Page, { key: view.value })],
        ),
      ])
  },
}

createApp(Harness).use(vuetify).mount('#app')
