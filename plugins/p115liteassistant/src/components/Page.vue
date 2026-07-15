<script setup>
import { computed, onMounted, ref } from 'vue'
import { pluginGet, pluginPost } from '../plugin.js'

const props = defineProps({ api: { type: Object, default: null }, show_switch: { type: Boolean, default: false } })
const emit = defineEmits(['switch', 'close', 'action'])
const status = ref({ running: [], history: [] })
const loading = ref(false)
const message = ref('')
const messageColor = ref('info')
const history = computed(() => status.value.history || [])
const runLabel = computed(() => status.value.running?.length ? status.value.running.join(' / ') : 'IDLE')

function tell(text, color = 'info') { message.value = text; messageColor.value = color }

async function refresh() {
  if (!props.api) return
  loading.value = true
  try { status.value = await pluginGet(props.api, '/status') } catch (error) { tell(error?.message || '状态获取失败', 'error') } finally { loading.value = false }
}

async function run(path, payload = {}) {
  try {
    const result = await pluginPost(props.api, path, payload)
    tell(result.message || '任务已开始', result.success ? 'success' : 'error')
    await refresh()
    emit('action')
  } catch (error) { tell(error?.message || '执行失败', 'error') }
}

onMounted(refresh)
</script>

<template>
  <div class="station-page">
    <header class="page-head">
      <div class="page-title"><span>115 DRIVE / TASK CONTROL</span><h2>运行台</h2></div>
      <div class="route-line" aria-label="运行链路"><b :class="{ online: status.authenticated }">115</b><i /><b :class="{ online: status.enabled }">302</b><i /><b :class="{ online: status.strm_mappings }">STRM</b></div>
      <div class="page-tools">
        <v-tooltip text="刷新状态" location="bottom"><template #activator="{ props: tipProps }"><v-btn v-bind="tipProps" icon="mdi-refresh" variant="text" size="small" :loading="loading" @click="refresh" /></template></v-tooltip>
        <v-tooltip v-if="show_switch" text="配置" location="bottom"><template #activator="{ props: tipProps }"><v-btn v-bind="tipProps" icon="mdi-tune-variant" variant="text" size="small" @click="emit('switch')" /></template></v-tooltip>
        <v-tooltip text="关闭" location="bottom"><template #activator="{ props: tipProps }"><v-btn v-bind="tipProps" icon="mdi-close" variant="text" size="small" @click="emit('close')" /></template></v-tooltip>
      </div>
    </header>

    <v-alert v-if="message" :type="messageColor" density="compact" variant="tonal" class="page-alert">{{ message }}</v-alert>

    <section class="state-ruler" aria-label="当前状态">
      <div><span>授权</span><strong :class="status.authenticated ? 'ok' : ''">{{ status.authenticated ? '已连接' : '未登录' }}</strong></div>
      <div><span>STRM 映射</span><strong>{{ status.strm_mappings || 0 }}</strong></div>
      <div><span>上传映射</span><strong>{{ status.upload_mappings || 0 }}</strong></div>
      <div><span>执行队列</span><strong class="mono" :class="{ running: status.running?.length }">{{ runLabel }}</strong></div>
    </section>

    <section class="command-deck" aria-label="执行任务">
      <button class="command command--strm" :disabled="status.running?.includes('strm')" @click="run('/strm/sync')"><v-icon icon="mdi-file-link-outline" size="23" /><span><b>生成 STRM</b><small>目录同步</small></span><v-icon icon="mdi-arrow-up-right" size="17" /></button>
      <button class="command" :disabled="status.running?.includes('upload')" @click="run('/upload', { incremental: false })"><v-icon icon="mdi-upload-outline" size="23" /><span><b>全量上传</b><small>重新扫描</small></span><v-icon icon="mdi-arrow-up-right" size="17" /></button>
      <button class="command" :disabled="status.running?.includes('upload')" @click="run('/upload', { incremental: true })"><v-icon icon="mdi-upload-network-outline" size="23" /><span><b>增量上传</b><small>仅变更项</small></span><v-icon icon="mdi-arrow-up-right" size="17" /></button>
      <button class="command command--checkin" @click="run('/checkin')"><v-icon icon="mdi-calendar-check-outline" size="23" /><span><b>立即签到</b><small>115 积分</small></span><v-icon icon="mdi-arrow-up-right" size="17" /></button>
    </section>

    <section class="ledger">
      <div class="ledger-head"><div><span>EXECUTION LOG</span><h3>最近记录</h3></div><span>{{ history.length }} 条</span></div>
      <div class="ledger-table" role="table">
        <div class="ledger-row ledger-label" role="row"><span>时间</span><span>类型</span><span>结果</span></div>
        <div v-for="(item, index) in history" :key="`${item.time}-${index}`" class="ledger-row" role="row">
          <time class="mono">{{ item.time }}</time>
          <span class="kind"><i />{{ item.kind }}</span>
          <span class="result">{{ item.message || `上传 ${item.uploaded || 0}，秒传 ${item.instant || 0}，删除 ${item.deleted || 0}，STRM ${item.added || 0}` }}</span>
        </div>
        <div v-if="!history.length" class="ledger-empty">暂无执行记录</div>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.station-page { --ink: #16211d; --muted: #64716a; --line: #c7d0ca; --soft-line: #dbe2de; --paper: #eef2f0; --green: #14946f; --cyan: #0d7483; --orange: #c9691a; color: var(--ink); background: var(--paper); border: 1px solid var(--line); font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; max-width: 1160px; padding: 25px 30px 30px; }
:global(.v-theme--dark) .station-page { --ink: #e7eee9; --muted: #9eaaa3; --line: #3c4a43; --soft-line: #2c3832; --paper: #18211d; --green: #54c79c; --cyan: #4dc5d5; --orange: #f0a95b; }
.page-head { display: grid; grid-template-columns: minmax(150px, 1fr) auto auto; align-items: center; gap: 24px; padding-bottom: 18px; border-bottom: 2px solid var(--ink); }.page-title > span, .ledger-head span { display: block; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; font-weight: 700; letter-spacing: .08em; }.page-title h2 { margin: 4px 0 0; font-size: 20px; font-weight: 760; }.route-line { display: flex; align-items: center; }.route-line b { color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }.route-line b.online { color: var(--cyan); }.route-line b.online::before { content: "● "; color: var(--green); font-size: 8px; }.route-line i { width: 28px; height: 1px; margin: 0 7px; background: var(--line); }.page-tools { display: flex; gap: 4px; }.page-tools :deep(.v-btn) { color: var(--muted); }.page-alert { margin-top: 16px; }
.state-ruler { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 23px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }.state-ruler div { display: flex; flex-direction: column; gap: 6px; min-height: 80px; padding: 16px 18px; border-right: 1px solid var(--line); }.state-ruler div:first-child { padding-left: 0; }.state-ruler div:last-child { border-right: 0; }.state-ruler span { color: var(--muted); font-size: 11px; font-weight: 650; }.state-ruler strong { font-size: 17px; font-weight: 760; overflow-wrap: anywhere; }.state-ruler strong.ok { color: var(--green); }.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 13px !important; }.running { color: var(--orange); }
.command-deck { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-top: 1px solid var(--line); border-left: 1px solid var(--line); }.command { display: grid; grid-template-columns: 28px minmax(0, 1fr) 18px; align-items: center; gap: 11px; min-height: 94px; padding: 15px; color: var(--ink); background: transparent; border: 0; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); cursor: pointer; text-align: left; transition: background .16s ease, color .16s ease; }.command:hover:not(:disabled) { color: var(--cyan); background: color-mix(in srgb, var(--cyan) 8%, transparent); }.command:disabled { color: var(--muted); cursor: not-allowed; }.command > span { display: grid; gap: 3px; min-width: 0; }.command b { font-size: 13px; }.command small { color: var(--muted); font-size: 11px; }.command--strm:hover:not(:disabled) { color: var(--green); background: color-mix(in srgb, var(--green) 9%, transparent); }.command--checkin:hover:not(:disabled) { color: var(--orange); background: color-mix(in srgb, var(--orange) 10%, transparent); }.command:focus-visible { outline: 2px solid var(--cyan); outline-offset: -2px; }
.ledger { margin-top: 30px; }.ledger-head { display: flex; justify-content: space-between; align-items: end; padding-bottom: 13px; border-bottom: 1px solid var(--line); }.ledger-head h3 { margin: 4px 0 0; font-size: 16px; }.ledger-head > span { color: var(--cyan); }.ledger-row { display: grid; grid-template-columns: 180px 110px minmax(0, 1fr); gap: 14px; align-items: center; min-height: 48px; border-bottom: 1px solid var(--soft-line); font-size: 12px; }.ledger-label { min-height: 33px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; font-weight: 700; letter-spacing: .04em; }.kind { display: inline-flex; align-items: center; gap: 7px; color: var(--cyan); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }.kind i { width: 6px; height: 6px; border-radius: 50%; background: var(--green); }.result { min-width: 0; overflow: hidden; color: var(--muted); text-overflow: ellipsis; white-space: nowrap; }.ledger-empty { padding: 36px 0; color: var(--muted); font-size: 13px; text-align: center; }
@media (max-width: 840px) { .station-page { padding: 22px 20px; }.page-head { grid-template-columns: 1fr auto; }.route-line { grid-column: 1 / -1; grid-row: 2; }.state-ruler { grid-template-columns: repeat(2, minmax(0, 1fr)); }.state-ruler div { padding: 14px; }.state-ruler div:first-child { padding-left: 14px; }.state-ruler div:nth-child(2) { border-right: 0; }.state-ruler div:nth-child(-n+2) { border-bottom: 1px solid var(--line); }.command-deck { grid-template-columns: repeat(2, minmax(0, 1fr)); }.ledger-row { grid-template-columns: 130px 90px minmax(0, 1fr); } }
@media (max-width: 560px) { .station-page { border-left: 0; border-right: 0; padding: 20px 16px; }.route-line i { width: 14px; margin: 0 4px; }.command-deck { grid-template-columns: 1fr; }.ledger-row { grid-template-columns: 1fr auto; gap: 5px 12px; padding: 10px 0; }.ledger-row time { grid-column: 1; }.ledger-row .kind { grid-column: 2; grid-row: 1; }.result { grid-column: 1 / -1; white-space: normal; }.ledger-label { display: none; } }
@media (prefers-reduced-motion: reduce) { .station-page * { transition: none !important; } }
</style>

<style scoped lang="scss">
.station-page {
  --ink: #172a34;
  --muted: #667b87;
  --line: #d5e1e7;
  --soft-line: #e8eff3;
  --paper: #eef4f7;
  --paper-strong: #ffffff;
  --header: #17333b;
  --green: #168c79;
  --cyan: #147fb8;
  --orange: #d88822;
  width: 100%;
  max-width: none;
  min-width: 0;
  box-sizing: border-box;
  padding: 0 34px 32px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper-strong);
  box-shadow: 0 14px 32px rgb(27 53 65 / 10%);
  font-family: "HarmonyOS Sans SC", "Microsoft YaHei", sans-serif;
}

:global(.v-theme--dark) .station-page {
  --ink: #e8f1f2;
  --muted: #a9b9bd;
  --line: #3a4b50;
  --soft-line: #2a383c;
  --paper: #172126;
  --paper-strong: #202d31;
  --header: #102b31;
  --green: #53c9ad;
  --cyan: #50bde8;
  --orange: #f0af5a;
  box-shadow: none;
}

.page-head {
  position: relative;
  grid-template-columns: minmax(210px, 1fr) auto auto;
  gap: 30px;
  min-height: 96px;
  margin: 0 -34px;
  padding: 16px 34px;
  color: #f5fbfc;
  background: var(--header);
  border: 0;
}
.page-head::after { position: absolute; right: 0; bottom: 0; left: 0; height: 3px; background: var(--cyan); content: ""; }
.page-title > span,
.ledger-head span { color: #a9c5ce; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; font-weight: 700; letter-spacing: .1em; }
.page-title h2 { margin-top: 3px; color: #fff; font-size: 23px; font-weight: 760; }
.route-line b { color: #a9c5ce; font-size: 11px; }
.route-line b.online { color: #fff; }
.route-line b.online::before { color: #60d2bb; }
.route-line i { width: 24px; margin: 0 8px; background: rgb(217 238 241 / 28%); }
.page-tools :deep(.v-btn) { color: #d8e8eb; }
.page-tools :deep(.v-btn:hover) { color: #fff; background: rgb(255 255 255 / 12%); }
.page-alert { margin-top: 18px; border-left: 3px solid var(--cyan); border-radius: 4px; }

.state-ruler { gap: 10px; margin: 26px 0; border: 0; }
.state-ruler div { min-height: 86px; padding: 16px; background: color-mix(in srgb, var(--paper) 65%, var(--paper-strong)); border: 1px solid var(--line); border-radius: 6px; }
.state-ruler div:first-child { padding-left: 16px; }
.state-ruler div:last-child { border-right: 1px solid var(--line); }
.state-ruler span { color: var(--muted); font-size: 11px; font-weight: 700; }
.state-ruler strong { font-size: 19px; font-weight: 760; }
.state-ruler strong.ok { color: var(--green); }
.mono { font-size: 12px !important; }
.running { color: var(--orange); }

.command-deck { gap: 10px; border: 0; }
.command { min-height: 118px; padding: 18px 15px; color: var(--ink); background: var(--paper-strong); border: 1px solid var(--line); border-radius: 6px; transition: transform .16s ease, border-color .16s ease, background .16s ease; }
.command:hover:not(:disabled) { color: var(--cyan); background: color-mix(in srgb, var(--cyan) 6%, var(--paper-strong)); border-color: var(--cyan); transform: translateY(-2px); }
.command--strm:hover:not(:disabled) { color: var(--green); background: color-mix(in srgb, var(--green) 7%, var(--paper-strong)); border-color: var(--green); }
.command--checkin:hover:not(:disabled) { color: var(--orange); background: color-mix(in srgb, var(--orange) 8%, var(--paper-strong)); border-color: var(--orange); }
.command:disabled { color: var(--muted); background: var(--paper); }
.command b { font-size: 13px; font-weight: 750; }
.command small { color: var(--muted); }
.command:focus-visible { outline-color: var(--cyan); }

.ledger { margin-top: 34px; }
.ledger-head { padding-bottom: 15px; border-bottom-color: var(--line); }
.ledger-head h3 { margin-top: 5px; font-size: 18px; }
.ledger-head > span { color: var(--cyan); }
.ledger-row { min-height: 52px; grid-template-columns: 190px 120px minmax(0, 1fr); padding: 0 12px; border-bottom-color: var(--soft-line); }
.ledger-row:not(.ledger-label):hover { background: color-mix(in srgb, var(--cyan) 5%, transparent); }
.ledger-label { min-height: 35px; padding: 0 12px; color: var(--muted); background: var(--paper); border-radius: 5px; }
.kind { color: var(--cyan); }
.kind i { background: var(--green); }
.result { color: var(--muted); }
.ledger-empty { padding: 44px 0; color: var(--muted); background: color-mix(in srgb, var(--paper) 58%, var(--paper-strong)); border: 1px dashed var(--line); border-radius: 6px; }

@media (max-width: 900px) {
  .station-page { border-radius: 0; }
  .page-head { grid-template-columns: minmax(0, 1fr) auto; }
  .route-line { grid-column: 1 / -1; grid-row: 2; }
  .state-ruler { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .state-ruler div { border-right: 1px solid var(--line); }
  .state-ruler div:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .command-deck { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 620px) {
  .station-page { padding: 0 16px 24px; border-right: 0; border-left: 0; }
  .page-head { min-height: 116px; margin: 0 -16px; padding: 15px 16px 14px; }
  .route-line i { width: 12px; margin: 0 5px; }
  .state-ruler { gap: 8px; margin: 20px 0; }
  .state-ruler div { min-height: 78px; padding: 13px; }
  .command-deck { grid-template-columns: 1fr; }
  .command { min-height: 84px; }
  .ledger { margin-top: 26px; }
  .ledger-row { grid-template-columns: 1fr auto; padding: 10px 4px; }
  .ledger-label { display: none; }
  .ledger-row .kind { grid-column: 2; grid-row: 1; }
  .result { grid-column: 1 / -1; white-space: normal; }
}

@media (prefers-reduced-motion: reduce) {
  .station-page * { transition: none !important; }
}
</style>
