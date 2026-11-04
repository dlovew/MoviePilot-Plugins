import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'DownloadSiteTagModdlovew',
      filename: 'remoteEntry.js',
      exposes: {
        './Config': './src/components/Config.vue'
      },
      shared: {
        vue: {
          requiredVersion: false,
          generate: false,
          singleton: true,
        },
        vuetify: {
          requiredVersion: false,
          generate: false,
          singleton: true,
        },
        'vuetify/styles': {
          requiredVersion: false,
          generate: false,
          singleton: true,
        },
      },
      format: 'esm'
    })
  ],
  build: {
    target: 'esnext',   // 联邦远程模块需要顶层 await
    minify: false,      // 开发阶段保留可读性
    cssCodeSplit: true,
    outDir: 'dist',
  },
  css: {
    postcss: {
      plugins: [
        {
          postcssPlugin: 'internal:charset-removal',
          AtRule: {
            charset: atRule => {
              if (atRule.name === 'charset') {
                atRule.remove()
              }
            }
          }
        },
        {
          // 官方范式：来自 vuetify / @mdi 的样式整块丢弃，其余仅过滤 .v- / .mdi- 规则，
          // 避免插件产物覆盖宿主前端的全局样式。
          postcssPlugin: 'vuetify-filter',
          Root(root) {
            const sourcePath = root.source?.input?.file?.replaceAll('\\', '/') || ''
            if (sourcePath.includes('/node_modules/vuetify/') || sourcePath.includes('/node_modules/@mdi/')) {
              root.nodes = []
              return
            }
            root.walkRules(rule => {
              if (rule.selector && (rule.selector.includes('.v-') || rule.selector.includes('.mdi-'))) {
                rule.remove()
              }
            })
          }
        }
      ]
    }
  },
  server: {
    port: 5001,
    cors: true,
    origin: 'http://localhost:5001'
  },
})
