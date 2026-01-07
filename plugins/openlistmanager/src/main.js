import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

const vuetify = createVuetify()

const app = createApp({
  template: '<div>OpenList管理器插件</div>'
})

app.use(vuetify)
app.mount('#app')
