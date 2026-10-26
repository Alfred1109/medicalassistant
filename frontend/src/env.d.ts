/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  // nginx 反向代理的路径前缀
  readonly VITE_API_PREFIX: string;
  // WebSocket 反向代理前缀
  readonly VITE_WS_URL: string;
  // Add more environment variables as needed
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
} 