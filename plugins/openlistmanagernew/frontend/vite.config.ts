import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'openlistmanagernew',
      filename: 'remoteEntry.js',
      exposes: {
        './Page': './src/Page.vue',
        './Config': './src/Config.vue',
        './Dashboard': './src/Dashboard.vue'
      },
      shared: ['vue']
    })
  ],
  build: {
    outDir: '../dist/assets',
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2022', // 支持顶层await
    rollupOptions: {
      output: {
        entryFileNames: '[name]-[hash].js',
        chunkFileNames: '[name]-[hash].js',
        assetFileNames: '[name]-[hash].[ext]'
      }
    }
  }
})