import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// Название установленного приложения (PWA) задаётся при сборке: манифест
// статический и не может взять его из профиля редакции во время работы.
// Остальное оформление приходит с сервера (GET /api/meta/edition).
const APPS = {
  base: {
    name: "e-archive — Электронный архив",
    short_name: "e-archive",
    description: "Электронный архив с AI-поиском, OCR и ЭЦП РК",
    theme_color: "#0e7490",
  },
  kazpost: {
    name: "Электронный архив АО «Казпочта»",
    short_name: "ЭА Казпочта",
    description: "ИС «Электронный архив» АО «Казпочта» (ТС-176)",
    theme_color: "#1f5aa8",
  },
};
const app = APPS[process.env.VITE_EDITION] || APPS.kazpost;

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        ...app,
        background_color: "#0f172a",
        display: "standalone",
        lang: "ru",
        icons: [
          { src: "favicon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" }
        ]
      }
    })
  ],
  server: {
    port: 3000,
    proxy: { "/api": "http://localhost:8000" }
  }
});
