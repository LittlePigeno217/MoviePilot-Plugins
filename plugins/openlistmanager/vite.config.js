import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'openlistmanager',
      filename: 'remoteEntry.js',
      exposes: {
        './Config': './src/Config.vue',
        './Status': './src/Status.vue'
      },
      shared: ['vue']
    })
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    target: 'esnext',
    minify: 'terser',
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        minifyInternalExports: false
      }
    },
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true
      }
    }
  },
  server: {
    port: 5173,
    open: true,
    cors: true
  }
})