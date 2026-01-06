import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Fix slow LAN loading by properly configuring HMR
    hmr: {
      host: '192.168.1.38', // Use your server's LAN IP
    },
    proxy: {
      '/api/chat': {
        target: 'http://localhost:8006',
        changeOrigin: true,
      },
      '/api/agent': {
        target: 'http://localhost:8009',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8006',
        changeOrigin: true,
      },
    },
  },
  // Optimize build for faster loading
  build: {
    target: 'esnext',
    minify: 'esbuild',
  },
})
