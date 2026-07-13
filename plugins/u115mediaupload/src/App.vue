<script setup>
import { computed, ref } from 'vue'
import Config from './components/Config.vue'
import Page from './components/Page.vue'
import AppPage from './components/AppPage.vue'
import LocalPathSelector from './components/LocalPathSelector.vue'
import P115PathSelector from './components/P115PathSelector.vue'

const activeTab = ref('console')

const tabs = [
  { value: 'console', label: '控制台' },
  { value: 'config', label: '配置' },
  { value: 'page', label: '状态' },
]

const tabComponent = computed(() => {
  if (activeTab.value === 'config') return Config
  if (activeTab.value === 'page') return Page
  return AppPage
})
</script>

<template>
  <v-app>
    <v-main class="u115-shell">
      <div class="u115-shell__top">
        <div>
          <div class="u115-shell__title">115媒体上传</div>
          <div class="u115-shell__subtitle">全量、增量、刮削和秒传控制台</div>
        </div>
        <v-btn-toggle v-model="activeTab" mandatory variant="tonal" density="comfortable">
          <v-btn v-for="tab in tabs" :key="tab.value" :value="tab.value">{{ tab.label }}</v-btn>
        </v-btn-toggle>
      </div>
      <component :is="tabComponent" />
    </v-main>
  </v-app>
</template>

<style scoped>
.u115-shell {
  min-height: 100vh;
  background: #f6f8f7;
  color: #17201c;
  padding: 20px;
}

.u115-shell__top {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.u115-shell__title {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0;
}

.u115-shell__subtitle {
  color: #5f6d67;
  margin-top: 4px;
}
</style>
