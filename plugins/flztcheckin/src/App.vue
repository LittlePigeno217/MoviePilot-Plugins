<template>
  <v-app>
    <v-main class="dev-shell">
      <div class="dev-shell__inner">
        <h1>Vue-FLZT自动签到</h1>
        <p>该前端用于 MoviePilot 插件远程组件开发，请在 MoviePilot 中安装并联调。</p>
      </div>
    </v-main>
  </v-app>
</template>

<style scoped>
.dev-shell {
  min-height: 100vh;
  background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
  color: #e5e7eb;
}

.dev-shell__inner {
  max-width: 720px;
  margin: 0 auto;
  padding: 72px 24px;
}

h1 {
  margin-bottom: 16px;
  font-size: 32px;
}

p {
  line-height: 1.7;
  color: #cbd5e1;
}
</style>
