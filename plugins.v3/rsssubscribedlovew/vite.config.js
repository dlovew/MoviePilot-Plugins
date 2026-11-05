import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'RssSubscribedlovew',
      filename: 'remoteEntry.js',
      exposes: {
        // V3 宿主在 vue 模式下：设置页加载 ./Config，数据页加载 ./Page，两者都必须暴露
        './Config': './src/components/Config.vue',
        './Page': './src/components/Page.vue'
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
    target: 'esnext',
    minify: false,
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
          // 官方范式：来自 vuetify / @mdi 的样式整块丢弃，其余过滤 .v- / .mdi- 规则，
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
    port: 5002,
    cors: true,
    origin: 'http://localhost:5002'
  },
})
