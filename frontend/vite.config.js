import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "e-archive — Электронный архив",
        short_name: "e-archive",
        description: "Электронный архив с AI-поиском, OCR и ЭЦП РК",
        theme_color: "#0e7490",
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
