import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
  plugins: [uni()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
    fs: {
      strict: true,
      allow: ['./', '../../node_modules', '../../knowledge/cards.json'].map((path) =>
        fileURLToPath(new URL(path, import.meta.url)),
      ),
    },
  },
})
