import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The backend (`python main.py --api`) listens on 127.0.0.1:8000 and has no CORS
// middleware, so the dev server proxies /api/* to it and strips the prefix.
const BACKEND = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
