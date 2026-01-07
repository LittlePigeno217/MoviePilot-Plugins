<template>
  <div id="app">
    <Config 
      v-if="showConfig"
      :initial-config="initialConfig"
      :openlist-available="openlistAvailable"
      @update:config="handleConfigUpdate"
    />
    <Status 
      v-else
      :api="api"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Config from './Config.vue'
import Status from './Status.vue'

const showConfig = ref(true)
const initialConfig = ref({})
const openlistAvailable = ref(false)
const api = ref(null)

const handleConfigUpdate = (newConfig) => {
  initialConfig.value = newConfig
}

onMounted(() => {
  window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'plugin-config') {
      initialConfig.value = event.data.config || {}
      openlistAvailable.value = event.data.openlistAvailable || false
      api.value = event.data.api || null
    }
  })
})
</script>

<style>
#app {
  width: 100%;
  height: 100%;
}
</style>
