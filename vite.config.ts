import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    const writeApiToken = (env.WRITE_API_TOKEN || '').trim();
    return {
      server: {
        port: 3001,
        host: '0.0.0.0',
        proxy: {
          '/api': {
            target: 'http://127.0.0.1:8000',
            changeOrigin: true,
            secure: false,
            configure: (proxy) => {
              proxy.on('proxyReq', (proxyReq) => {
                if (writeApiToken) {
                  proxyReq.setHeader('X-Write-Token', writeApiToken);
                }
              });
            },
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
