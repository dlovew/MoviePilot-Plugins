# 下载任务分类与标签魔改 VUE 版 -dlovew

基于官方 `DownloadSiteTag` 魔改的自用插件，按站点 / 分类为下载任务自动设置 qBittorrent 标签与二级分类。V3 专用实现，使用 Vue 联邦远程组件作为配置页。

## 目录结构

```text
downloadsitetagmoddlovew/
├── __init__.py                     # 插件主类，get_render_mode() 返回 ("vue", "dist/assets")
├── src/components/Config.vue       # 配置页源码（联邦暴露 ./Config）
├── src/main.js                     # 本地预览入口，仅 npm run preview 使用
├── vite.config.js / package.json   # 联邦构建工程
├── dist/assets/                    # 构建产物，必须包含 remoteEntry.js
├── dist/index.html                 # 本地预览产物，宿主不加载
├── index.html                      # Vite 构建入口
└── README.md
```

## 开发

```bash
yarn install                        # 或 npm install --no-package-lock
yarn dev                            # vite build --watch，配合 PLUGIN_LOCAL_REPO_PATHS 联调
yarn build                          # 重新生成 dist/，提交产物
```

构建产物只包含 ESM 远程模块，不含 Vuetify 全局样式；`dist/index.html` 与入口 JS 仅供本地预览，宿主只加载 `dist/assets/remoteEntry.js`。

构建要求（见 `MoviePilot-Frontend/docs/module-federation-guide.md`）：

- `format: 'esm'`、`filename: 'remoteEntry.js'`、`build.target: 'esnext'`；
- 共享 `vue` / `vuetify`，`generate: false`，不得打包 Vuetify 全局样式；
- 只暴露 `./Config`，产物放在 `dist/assets/`。

## V3 配置契约

- 配置由宿主 `GET plugin/form/{id}` 注入 `initialConfig`，组件不得自行请求 `plugin/{id}/config`；
- 保存用 `emit('save', config)`，宿主统一 `PUT plugin/{id}`；
- 调用插件自定义 API 时使用 `api` prop 与 `pluginId`（实例作用域），例如
  `props.api.post(\`plugin/${props.pluginId}/reset_categories\`)`，不要硬编码类名；
- 插件后端只注册 `/reset_categories`（`auth: "bear"`），服务 ID 按 `self.__class__.__name__` 动态生成，支持分身。

## 已知依赖

分类列表与分类计算使用 V3 宿主 `app.modules.themoviedb.category.CategoryHelper` 的只读兼容门面（该门面在 V3 只读且拒绝写入 `category.yaml`）。若宿主从未来版本移除该门面，需要改用版本化分类策略 API。
