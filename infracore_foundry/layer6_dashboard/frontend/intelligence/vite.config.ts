import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const API_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8006'
const WS_TARGET = process.env.VITE_WS_PROXY_TARGET || 'ws://localhost:8006'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@shared': path.resolve(__dirname, '../shared/src'),
    },
  },
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      '/ws': { target: WS_TARGET, ws: true, changeOrigin: true },
    },
  },
})
