import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    return {
      server: {
        port: 3001,
        host: '0.0.0.0',
        proxy: {
          '/api': {
            target: 'http://127.0.0.1:8000',
            changeOrigin: true,
            secure: false,
          }
        }
      },
      plugins: [react()],
      define: {
        'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
        'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, 'src'),
        }
      },
      build: {
        rollupOptions: {
          output: {
            manualChunks(id) {
              if (id.includes('/node_modules/echarts/')) {
                return 'vendor-echarts';
              }
              if (id.includes('/node_modules/zrender/')) {
                return 'vendor-zrender';
              }
              if (id.includes('/node_modules/recharts/')) {
                return 'vendor-recharts';
              }
              if (id.includes('/node_modules/lucide-react/')) {
                return 'vendor-ui';
              }
            },
          },
        },
      }
    };
});
