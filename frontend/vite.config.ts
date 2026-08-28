import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import { fileURLToPath, URL } from "node:url";

// 构建产物输出到 FastAPI 主服务侧的 app/web_vue 目录。
// 后端未来可以选择挂载到 /ui-vue/,也可以直接替换 /ui/。
// 这里采用相对 base,产物在任意 URL 前缀下都能解析静态资源。
export default defineConfig({
  base: "./",
  plugins: [
    vue(),
    AutoImport({
      imports: ["vue", "vue-router", "pinia"],
      resolvers: [ElementPlusResolver()],
      dts: "src/auto-imports.d.ts",
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: "src/components.d.ts",
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发期把 /api 代理到本地 FastAPI 服务(uv run uvicorn ...)
      "/api": {
        target: "http://127.0.0.1:8020",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../app/web_vue",
    emptyOutDir: true,
    sourcemap: false,
    target: "es2020",
    chunkSizeWarningLimit: 1500,
  },
});
