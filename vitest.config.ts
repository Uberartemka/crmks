import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

export default defineConfig({
  plugins: [
    vue({
      template: {
        compilerOptions: {
          // vue-advanced-chat ships as a web component; tell the Vue compiler
          // not to resolve these tags as native Vue components.
          isCustomElement: (tag: string) =>
            tag === 'vue-advanced-chat' || tag === 'emoji-picker',
        },
      },
    }),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'jsdom',
  },
})
