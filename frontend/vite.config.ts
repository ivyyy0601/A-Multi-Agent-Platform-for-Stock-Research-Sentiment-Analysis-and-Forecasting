import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/',
  plugins: [
    react({
      babel: {
        plugins: [['babel-plugin-react-compiler']],
      },
    }),
  ],
  server: {
    port: 7777,
    proxy: {
      // Analysis backend (port 8001) — must be before /api
      '/api/v1': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      // Main PokieTicker backend (port 8000)
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Adanos external API proxy (avoids browser CORS)
      '/adanos': {
        target: 'https://api.adanos.org',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/adanos/, ''),
      },
    },
  },
})
