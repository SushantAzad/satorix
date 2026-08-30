// Programmatic Vite startup: no npm lifecycle scripts, config files or dotenv loading.
import { pathToFileURL } from 'node:url'
const [app, portText] = process.argv.slice(2)
if (!['intelligence', 'operational', 'schema'].includes(app) || process.env.LOCAL_SAFE_MODE !== 'true') throw new Error('Safe frontend configuration required')
const root = `/frontend/${app}`
const { createServer } = await import(pathToFileURL(`${root}/node_modules/vite/dist/node/index.js`).href)
const server = await createServer({
  root, configFile: false, envDir: '/tmp/no-dotenv', cacheDir: `/tmp/vite-${app}`,
  define: { 'import.meta.env.VITE_LOCAL_SAFE_MODE': JSON.stringify('true'), 'import.meta.env.VITE_API_URL': JSON.stringify('/'), 'import.meta.env.VITE_WS_URL': JSON.stringify('') },
  resolve: {
    alias: { '@': `${root}/src`, '@shared': '/frontend/shared/src' },
    // Shared source files resolve through /frontend/node_modules while each app
    // has its own dependency volume. Force one React runtime per Vite app.
    dedupe: ['react', 'react-dom'],
  },
  server: { host: '0.0.0.0', port: Number(portText), strictPort: true, hmr: false,
    fs: { allow: ['/frontend'] },
    headers: { 'Content-Security-Policy': "default-src 'self'; connect-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'self'", 'Referrer-Policy': 'no-referrer' },
    proxy: { '/api': { target: 'http://layer6-api:8006', changeOrigin: true } }
  }
})
await server.listen()
server.printUrls()
