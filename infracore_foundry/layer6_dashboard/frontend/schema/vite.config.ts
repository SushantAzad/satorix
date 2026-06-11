import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const API_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8006'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@shared': path.resolve(__dirname, '../shared/src'),
    },
  },
  server: {
    port: 3002,
    host: true,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
})
