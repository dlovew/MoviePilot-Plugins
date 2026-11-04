import { createApp, h } from 'vue'
import Config from './components/Config.vue'

// 仅用于 `npm run preview` 本地预览；宿主加载的是联邦暴露的 ./Config 远程组件。
const api = {
  get: async () => ({}),
  post: async () => ({}),
}

createApp({
  render: () => h(Config, {
    api,
    initialConfig: { name: '下载任务分类与标签魔改VUE版 -dlovew' },
    pluginId: 'DownloadSiteTagModdlovew',
  }),
}).mount('#app')
