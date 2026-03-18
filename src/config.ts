// 统一管理后端 API 地址
// 开发环境：使用 Vite 代理 (/api -> http://localhost:8000/api) 或直接连接
// 生产环境：使用相对路径 /api (由 Nginx 代理)

export const API_BASE_URL = import.meta.env.PROD ? '/api' : '/api';

const WRITE_TOKEN_SESSION_KEY = 'market_admin_write_token';

const isBrowser = (): boolean => typeof window !== 'undefined';

export const getStoredWriteToken = (): string => {
  if (!isBrowser()) return '';
  return (window.sessionStorage.getItem(WRITE_TOKEN_SESSION_KEY) || '').trim();
};

export const setStoredWriteToken = (token: string): void => {
  if (!isBrowser()) return;
  const normalized = token.trim();
  if (!normalized) {
    window.sessionStorage.removeItem(WRITE_TOKEN_SESSION_KEY);
    return;
  }
  window.sessionStorage.setItem(WRITE_TOKEN_SESSION_KEY, normalized);
};

export const clearStoredWriteToken = (): void => {
  if (!isBrowser()) return;
  window.sessionStorage.removeItem(WRITE_TOKEN_SESSION_KEY);
};

export const getWriteHeaders = (withJson: boolean = false): Record<string, string> => {
  const headers: Record<string, string> = {};
  if (withJson) {
    headers['Content-Type'] = 'application/json';
  }
  const writeToken = getStoredWriteToken();
  if (writeToken) {
    headers['X-Write-Token'] = writeToken;
  }
  return headers;
};
