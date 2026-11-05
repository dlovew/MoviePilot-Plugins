import { createApp, h } from 'vue'
import Config from './components/Config.vue'

// 仅用于 `npm run preview` 本地预览；宿主加载的是联邦暴露的 ./Config 与 ./Page。
const api = {
  get: async () => ({}),
  post: async () => ({}),
}

createApp({
  render: () => h(Config, {
    api,
    initialConfig: {},
    pluginId: 'RssSubscribedlovew',
  }),
}).mount('#app')
