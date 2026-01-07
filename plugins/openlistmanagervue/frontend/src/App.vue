<template>
  <v-app>
    <v-main>
      <v-container>
        <v-card>
          <v-card-title>OpenList管理器 - 本地开发</v-card-title>
          <v-card-text>
            <v-alert type="info" class="mb-4">
              这是本地开发环境，用于测试组件功能
            </v-alert>
            <v-tabs v-model="tab">
              <v-tab value="page">Page组件</v-tab>
              <v-tab value="config">Config组件</v-tab>
              <v-tab value="dashboard">Dashboard组件</v-tab>
            </v-tabs>
            <v-window v-model="tab">
              <v-window-item value="page">
                <Page />
              </v-window-item>
              <v-window-item value="config">
                <Config />
              </v-window-item>
              <v-window-item value="dashboard">
                <Dashboard />
              </v-window-item>
            </v-window>
          </v-card-text>
        </v-card>
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref } from 'vue'
import Page from './components/Page.vue'
import Config from './components/Config.vue'
import Dashboard from './components/Dashboard.vue'

const tab = ref('page')
</script>
