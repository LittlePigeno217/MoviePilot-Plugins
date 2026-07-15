import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import Config from './components/Config.vue'

createApp(Config).use(createVuetify({ components, directives })).mount('#app')
