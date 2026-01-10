<script setup lang="ts">
// 接收配置和刷新控制
defineProps({
  config: {
    type: Object,
    default: () => ({})
  },
  allowRefresh: {
    type: Boolean,
    default: true
  }
})

// 仪表板逻辑...
</script>

<template>
  <div class="dashboard-widget">
    <v-hover>
      <!-- 仪表板内容 -->
      <template #default="{ isHovering, props: hoverProps }">
        <v-card v-bind="hoverProps">
          <v-card-title>{{ config.title || 'OpenList扩展' }}</v-card-title>
          <v-card-text>
            <!-- 组件内容 -->
            <div class="text-center py-4">
              <v-icon size="40" color="primary">mdi-folder-open</v-icon>
              <div class="mt-2">OpenList管理器扩展</div>
              <div class="text-caption text-muted">增强OpenList管理功能</div>
            </div>
          </v-card-text>
          <!-- 只在悬停时显示拖拽图标 -->
          <div v-show="isHovering" class="absolute right-5 top-5">
            <v-icon class="cursor-move">mdi-drag</v-icon>
          </div>
        </v-card>
      </template>
    </v-hover>
  </div>
</template>

<style scoped>
.dashboard-widget {
  padding: 10px;
}
</style>