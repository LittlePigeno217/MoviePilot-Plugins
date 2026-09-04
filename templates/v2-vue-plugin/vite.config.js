import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

export default defineConfig({
  plugins: [
    vue(),
    federation({
      // 改成你的插件类名（与后端 __init__.py 里的类名、根 package.json 的键一致）
      name: 'TemplatePlugin',
      filename: 'remoteEntry.js',
      exposes: {
        './Page': './src/components/Page.vue',
        './Config': './src/components/Config.vue',
      },
      // 只声明代码里真正 import 的依赖。这里曾经还有 'vuetify/styles'，但远程模块
      // 从来没 import 过它（只有 main.js 那个调试壳会），声明反而让 federation 把
      // Vuetify 基础样式表整份内联进产物：CSS 340KB+，而且那份 CSS 没有插件的命名
      // 空间，会盖住 MoviePilot 自己的 Vuetify 样式。别加回来。
      shared: {
        vue: { requiredVersion: false, generate: false },
        vuetify: { requiredVersion: false, generate: false, singleton: true },
      },
      format: 'esm',
    }),
  ],
  build: {
    target: 'esnext',
    // 插件产物走公网仓库下发，不压缩等于让每个用户多下几倍体积
    minify: 'esbuild',
    cssCodeSplit: false,
    // 产物只要联邦远程模块，不要 index.html 那个调试壳。
    //
    // index.html -> src/main.js 是 `npm run dev` 用的独立外壳，它 import 了整个
    // vuetify。让它进构建的话 dist 会多出 1MB 级的 index.js + 121KB 的图标解析
    // 代码，而 remoteEntry 还会把合并后的 CSS <link> 进宿主 head。
    //
    // input 留空即可：remoteEntry 由 vite-plugin-federation 在 buildStart 里
    // emitFile 单独产出，不依赖 rollup input。
    rollupOptions: { input: {} },
  },
  // 没有 postcss 的 vuetify-filter：那是旧构建把整份 Vuetify 打进产物时，事后删掉所有
  // 含 `.v-` 规则的兜底手段。现在产物里本来就没有 Vuetify 基础样式，那个过滤器反而会把
  // kit.scss 里 `.tpl .v-btn {…}` 这类命名空间内的收敛规则一并删掉。
  server: { port: 5099, cors: true, origin: 'http://localhost:5099' },
})
