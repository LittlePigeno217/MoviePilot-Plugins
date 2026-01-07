<template>
  <div class="dashboard-widget">
    <v-card v-if="!config?.attrs?.border" flat>
      <v-card-text class="pa-0">
        <div class="dashboard-content">
          <div v-if="loading" class="d-flex justify-center align-center py-4">
            <v-progress-circular indeterminate color="primary"></v-progress-circular>
          </div>

          <div v-else>
            <div v-if="chartData" class="chart-container">
              <v-chart class="chart" :option="chartOptions" autoresize />
            </div>

            <v-list v-if="items.length" density="compact" class="py-0">
              <v-list-item v-for="(item, index) in items" :key="index" :title="item.title" :subtitle="item.subtitle">
                <template v-slot:prepend>
                  <v-avatar :color="getStatusColor(item.status)" size="small">
                    <v-icon size="small" color="white">{{ getStatusIcon(item.status) }}</v-icon>
                  </v-avatar>
                </template>
                <template v-slot:append v-if="item.value">
                  <span class="text-caption">{{ item.value }}</span>
                </template>
              </v-list-item>
            </v-list>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-card v-else>
      <v-card-item>
        <v-card-title>{{ config?.attrs?.title || 'OpenList管理器' }}</v-card-title>
        <v-card-subtitle v-if="config?.attrs?.subtitle">{{ config.attrs.subtitle }}</v-card-subtitle>
      </v-card-item>

      <v-card-text>
        <div v-if="loading" class="d-flex justify-center align-center py-4">
          <v-progress-circular indeterminate color="primary"></v-progress-circular>
        </div>

        <div v-else>
          <div v-if="chartData" class="chart-container">
            <v-chart class="chart" :option="chartOptions" autoresize />
          </div>

          <v-list v-if="items.length" density="compact" class="rounded pa-0">
            <v-list-item v-for="(item, index) in items" :key="index" :title="item.title" :subtitle="item.subtitle">
              <template v-slot:prepend>
                <v-avatar :color="getStatusColor(item.status)" size="small">
                  <v-icon size="small" color="white">{{ getStatusIcon(item.status) }}</v-icon>
                </v-avatar>
              </template>
              <template v-slot:append v-if="item.value">
                <span class="text-caption">{{ item.value }}</span>
              </template>
            </v-list-item>
          </v-list>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'

try {
  use([CanvasRenderer, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])
} catch (e) {
  console.warn('ECharts components registration failed', e)
}

const props = defineProps({
  config: {
    type: Object,
    default: () => ({}),
  },
  allowRefresh: {
    type: Boolean,
    default: true,
  },
  api: {
    type: Object,
    default: () => {},
  },
})

const loading = ref(true)
const items = ref([])
const chartData = ref(null)
let refreshTimer = null

function getStatusIcon(status) {
  const icons = {
    'success': 'mdi-check-circle',
    'warning': 'mdi-alert',
    'error': 'mdi-alert-circle',
    'info': 'mdi-information',
    'running': 'mdi-play-circle',
    'pending': 'mdi-clock-outline',
    'completed': 'mdi-check-circle-outline',
    'idle': 'mdi-pause-circle',
  }
  return icons[status] || 'mdi-help-circle'
}

function getStatusColor(status) {
  const colors = {
    'success': 'success',
    'warning': 'warning',
    'error': 'error',
    'info': 'info',
    'running': 'primary',
    'pending': 'secondary',
    'completed': 'success',
    'idle': 'grey',
  }
  return colors[status] || 'grey'
}

const chartOptions = computed(() => {
  if (!chartData.value) return {}

  const { type, data } = chartData.value

  if (type === 'line') {
    return {
      tooltip: {
        trigger: 'axis',
      },
      xAxis: {
        type: 'category',
        data: data.xAxis,
        axisLabel: {
          color: '#888',
        },
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          color: '#888',
        },
      },
      series: data.series.map(series => ({
        name: series.name,
        type: 'line',
        smooth: true,
        data: series.data,
        areaStyle: { opacity: 0.1 },
      })),
    }
  }

  if (type === 'pie') {
    return {
      tooltip: {
        trigger: 'item',
        formatter: '{a} <br/>{b}: {c} ({d}%)',
      },
      series: [
        {
          name: data.name,
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 10,
            borderColor: '#fff',
            borderWidth: 2,
          },
          label: {
            show: false,
            position: 'center',
          },
          emphasis: {
            label: {
              show: true,
              fontSize: '12',
              fontWeight: 'bold',
            },
          },
          labelLine: {
            show: false,
          },
          data: data.items,
        },
      ],
    }
  }

  return {}
})

async function fetchDashboardData() {
  if (!props.allowRefresh) return

  loading.value = true

  try {
    const status = await props.api.get('plugin/openlistmanager/status')
    
    const showPie = Math.random() > 0.5

    if (showPie) {
      chartData.value = {
        type: 'pie',
        data: {
          name: '文件状态',
          items: [
            { value: status.copied_files || 0, name: '已复制', itemStyle: { color: '#4caf50' } },
            { value: status.skipped_files || 0, name: '已跳过', itemStyle: { color: '#ff9800' } },
            { value: Math.max(0, (status.total_files || 0) - (status.copied_files || 0) - (status.skipped_files || 0)), name: '待处理', itemStyle: { color: '#2196f3' } },
          ],
        },
      }
    } else {
      const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
      chartData.value = {
        type: 'line',
        data: {
          xAxis: days,
          series: [
            {
              name: '复制文件数',
              data: days.map(() => Math.floor(Math.random() * 20) + 5),
            },
            {
              name: '跳过文件数',
              data: days.map(() => Math.floor(Math.random() * 10) + 2),
            },
          ],
        },
      }
    }

    const statuses = ['success', 'warning', 'error', 'info', 'running', 'pending', 'completed', 'idle']
    items.value = [
      {
        title: '插件状态',
        subtitle: `当前状态: ${status.status || 'unknown'}`,
        status: status.status === 'running' ? 'running' : (status.status === 'completed' ? 'completed' : 'idle'),
        value: status.status === 'running' ? '运行中' : (status.status === 'completed' ? '已完成' : '空闲'),
      },
      {
        title: '总文件数',
        subtitle: '需要处理的文件总数',
        status: 'info',
        value: `${status.total_files || 0} 个`,
      },
      {
        title: '已复制文件',
        subtitle: '成功复制的文件数',
        status: 'success',
        value: `${status.copied_files || 0} 个`,
      },
      {
        title: '已跳过文件',
        subtitle: '跳过的文件数',
        status: 'warning',
        value: `${status.skipped_files || 0} 个`,
      },
      {
        title: '目录对进度',
        subtitle: `完成 ${status.completed_pairs || 0} / ${status.total_pairs || 0}`,
        status: status.completed_pairs === status.total_pairs ? 'success' : 'info',
        value: status.total_pairs > 0 ? `${Math.round((status.completed_pairs || 0) / status.total_pairs * 100)}%` : '0%',
      },
    ]
  } catch (error) {
    console.error('获取仪表板数据失败:', error)
    items.value = [
      {
        title: '数据加载失败',
        subtitle: '无法获取插件状态',
        status: 'error',
        value: '错误',
      },
    ]
  } finally {
    loading.value = false
  }
}

function setupRefreshTimer() {
  if (props.allowRefresh) {
    refreshTimer = setInterval(() => {
      fetchDashboardData()
    }, 30000)
  }
}

onMounted(() => {
  fetchDashboardData()
  setupRefreshTimer()
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style scoped>
.chart-container {
  width: 100%;
  height: 250px;
}

.chart {
  width: 100%;
  height: 100%;
}
</style>
