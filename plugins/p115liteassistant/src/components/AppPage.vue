<script setup>
/**
 * 全页外壳 —— MoviePilot 侧栏入口 /plugin-app/P115LiteAssistant 落到这里。
 *
 * 全页只有媒体清单一页，不再有分区导轨。设置仍由标题栏那个按钮进出（它自己已经是一条
 * 导轨，导轨套导轨没法读）。
 *
 * 别的几块（总览的手动按钮与审阅账本、任务台的实时日志、文件浏览、网盘管理）组件都还在
 * 仓库里，只是没挂到这一页上；插件列表里那张卡片渲染的还是原来的运行台，手动触发和审阅
 * 账本仍然在那儿。后端那些接口也照旧注册着，要把某一块接回来只是加一个入口的事。
 *
 * 这里只干三件事：拿着视图状态、把宿主注入的 prop 声明掉（否则会漏成根节点的 DOM 属性）、
 * 读一份 /status 供标题栏和清单共用（清单要知道有没有 115 任务在跑，好禁用会抢锁的动作）。
 */
import { computed, inject, reactive, ref } from 'vue'
import AppBar from './ui/AppBar.vue'
import Config from './Config.vue'
import DiskDesk from './DiskDesk.vue'
import FileDesk from './FileDesk.vue'
import MediaLedger from './MediaLedger.vue'
import TaskDesk from './TaskDesk.vue'
import { pluginGet, useHostNotice } from '../plugin.js'
import '../styles/kit.scss'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  pluginId: { type: String, default: '' },
  navKey: { type: String, default: 'main' },
  nativeSubscribe: { type: [Object, Function], default: null },
})

const view = ref('work')
const configWidth = ref('')
const reloadToken = ref(0)
const busy = ref(false)
const status = ref({})
const ready = ref(false)
const failed = ref(false)

const trusted = computed(() => ready.value && !failed.value)
// strm / upload / sweep 共用同一把 115 数据任务锁，任何一个在跑其它都起不来
const working = computed(() =>
  (status.value.running || []).some(kind => ['strm', 'upload', 'sweep'].includes(kind)),
)

/**
 * 三件工具：清单管不了的事归它们。做成叠层而不是分区，页面的内容仍然只有清单一页 ——
 * 你得主动打开才会看见它们。
 *
 *   文件  浏览 115 与本地目录，不建通道就跑一次同步或上传
 *   网盘  当网盘用：浏览、新建、改名、删除
 *   日志  正在跑什么 + 插件日志实时看
 */
const TOOLS = [
  { key: 'files', label: '文件', icon: 'mdi-folder-search-outline' },
  { key: 'disk', label: '网盘', icon: 'mdi-cloud-outline' },
  { key: 'tasks', label: '日志', icon: 'mdi-text-box-outline' },
]
const tool = ref('')
const currentTool = computed(() => TOOLS.find(item => item.key === tool.value) || null)

const local = reactive({ text: '', kind: 'info' })
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text
  local.kind = kind
})

async function loadStatus() {
  if (!props.api) return
  busy.value = true
  try {
    status.value = await pluginGet(props.api, '/status')
    failed.value = false
  } catch (error) {
    failed.value = true
  } finally {
    busy.value = false
    ready.value = true
  }
}

function refresh() {
  reloadToken.value += 1
  loadStatus()
}

function say(event) {
  notice.say(event?.text || '', event?.kind || 'info')
}

loadStatus()
</script>

<template>
  <div class="p115 app">
    <div class="app__shell" :style="view === 'config' && configWidth ? { maxWidth: configWidth } : null">
      <template v-if="view === 'work'">
        <AppBar
          view="清单"
          :online="Boolean(status.authenticated)"
          :probing="!trusted"
          :busy="busy"
          :show-close="false"
          show-refresh
          @refresh="refresh"
          @switch="view = 'config'"
        >
          <template #tools>
            <v-menu location="bottom end">
              <template #activator="{ props: menu }">
                <v-btn v-bind="menu" variant="text" size="small" append-icon="mdi-menu-down">工具</v-btn>
              </template>
              <v-list density="compact" class="p115 p115-portal">
                <v-list-item
                  v-for="item in TOOLS"
                  :key="item.key"
                  :prepend-icon="item.icon"
                  :title="item.label"
                  @click="tool = item.key"
                />
              </v-list>
            </v-menu>
          </template>
        </AppBar>

        <button
          v-if="local.text"
          type="button"
          class="app__local"
          :class="`app__local--${local.kind}`"
          @click="local.text = ''"
        >
          {{ local.text }}
          <span class="app__local-dismiss">知道了</span>
        </button>

        <div class="app__body">
          <MediaLedger
            :api="props.api"
            :busy="working"
            :reload-token="reloadToken"
            :pending="status.pending_deletes || []"
            @notice="say"
            @done="loadStatus"
          />
        </div>
      </template>

      <!-- 设置页照它自己报的宽度限住并居中：表单铺满整屏只会更难读 -->
      <Config
        v-else-if="view === 'config'"
        class="app__config"
        :api="props.api"
        wide
        @switch="view = 'work'"
        @layout="event => (configWidth = String(event?.maxWidth || ''))"
      />
    </div>

    <Teleport to="body">
      <div v-if="tool" class="app__tool p115 p115-portal" @click.self="tool = ''">
        <section class="app__tool-box" role="dialog" aria-modal="true">
          <header class="app__tool-head">
            <div>
              <span class="p115-label">工具</span>
              <h3 class="p115-section-title">{{ currentTool?.label }}</h3>
            </div>
            <v-btn variant="text" size="small" icon="mdi-close" aria-label="关闭" @click="tool = ''" />
          </header>
          <div class="app__tool-body">
            <FileDesk
              v-if="tool === 'files'"
              :api="props.api"
              :busy="working"
              :reload-token="reloadToken"
              @notice="say"
              @done="loadStatus"
            />
            <DiskDesk
              v-else-if="tool === 'disk'"
              :api="props.api"
              :reload-token="reloadToken"
              @notice="say"
            />
            <TaskDesk
              v-else
              :api="props.api"
              :status="status"
              :trusted="trusted"
              :probe-note="probeNote"
              :reload-token="reloadToken"
            />
          </div>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
// 铺满宿主给的整块区域：不限宽、不留外边距、不套卡片。
// 也**不要 overflow** —— 它会造出一个滚动容器，把标题栏、吸顶条、表头的 sticky 全废掉，
// 而 385 行的清单里那三条吸顶正是最要紧的。
.app {
  background: var(--p115-paper);
  min-height: 100%;
}

.app__shell {
  min-height: 100%;
}

.app__body {
  padding: 0;
}

// 宿主消息条缺席时（独立联调）退回这一条，点一下收起
.app__config {
  max-width: 58rem;
  margin-inline: auto;
}

.app__local {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 16px;
  border: 0;
  border-bottom: 1px solid var(--p115-hairline);
  background: var(--p115-faint);
  color: inherit;
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.app__local--success { color: rgb(var(--v-theme-success)); }
.app__local--error { color: rgb(var(--v-theme-error)); }

.app__local-dismiss {
  margin-inline-start: auto;
  color: var(--p115-muted);
}

// 工具叠层：页面的内容仍然只有清单，这几件要主动打开才出现
.app__tool {
  position: fixed;
  inset: 0;
  z-index: 2450;
  display: grid;
  place-items: start center;
  padding: 20px 16px 32px;
  overflow: auto;
  background: rgba(0, 0, 0, 0.45);
}

.app__tool-box {
  width: min(1400px, 96vw);
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius);
  background: var(--p115-paper);
  box-shadow: var(--p115-shadow);
  overflow: hidden;
}

.app__tool-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 0;
}

.app__tool-body {
  padding: 12px 18px 18px;
}


</style>
