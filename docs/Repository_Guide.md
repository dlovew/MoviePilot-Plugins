# 仓库指南（V3 专用）

本文档面向本仓库维护者，说明 `dlovew/MoviePilot-Plugins` 在 MoviePilot 体系中的职责、目录约定、元数据规则、门禁与发布流程。本仓库**只维护 V3 插件**，V2 插件目录、索引、文档与测试已全部移除。

## 1. 职责边界

本仓库不是运行时，只提供插件源码、市场索引、图标和文档。

- `MoviePilot`（后端）：插件类加载与生命周期、事件与链式扩展、动态 API / 服务 / 仪表板注册、配置与数据持久化、插件安装与远程组件静态资源服务。
- `MoviePilot-Frontend`（前端）：插件市场、配置页 / 数据页 / 仪表板渲染、Vue 联邦远程组件加载、侧栏全页入口。
- 本仓库：`plugins.v3/`、`package.v3.json`、`icons/`、`docs/`、`tests/`、CI 工作流。

排查问题时按边界定位：`get_api()` 未挂载或配置保存异常查后端 `app/api/endpoints/plugin.py` 与 `app/runtime/extensions/plugin/`；远程组件不显示查前端 `docs/module-federation-guide.md` 与 `src/utils/federationLoader.ts`；插件不出现在市场才查本仓库 `package.v3.json`。

## 2. 目录结构

```text
MoviePilot-Plugins/
├── plugins.v3/                     # V3 插件源码，一个插件一个目录
│   └── <plugin_id_lower>/
│       ├── __init__.py             # 必须，插件主类定义处
│       ├── README.md               # 可选
│       ├── pyproject.toml          # 可选，V3 额外依赖（不是 requirements.txt）
│       └── dist/assets/            # 可选，Vue 联邦构建产物（含 remoteEntry.js）
├── icons/                          # 插件图标
├── docs/                           # 开发指南、仓库指南、FAQ
├── tests/                          # 契约测试，不放在插件目录内
├── .github/scripts/                # 版本门禁脚本
├── .github/workflows/              # PR 门禁与 Release
├── .githooks/pre-push              # 本地 push 前的版本门禁
├── package.v3.json                 # V3 市场索引（唯一有效索引）
└── package.json                    # 空对象占位，供宿主回退请求使用
```

硬约定：

- 插件 ID = 类名 = `package.v3.json` 的对象键，目录名为 ID 全小写，ID 匹配 `^[A-Za-z][A-Za-z0-9_]{0,127}$`。
- 主类必须定义在 `plugins.v3/<id小写>/__init__.py`，且继承 `_PluginBase`。
- 宿主按代际选择索引与源码目录；本仓库只提供 `package.v3.json` 与 `plugins.v3/`，`package.json` 保留空 `{}` 以避免宿主回退请求时产生 404。
- 测试一律放 `tests/`，插件目录会整目录拷贝到运行时副本，不能夹带测试文件。
- 展示名带 `-dlovew` 后缀，作者统一 `dlovew`；命名空间、API 路径、服务 ID 一律用 `self.__class__.__name__` 或注入的 `pluginId`，不硬编码原 ID，以支持插件分身。

## 3. 市场索引字段

`package.v3.json` 是「插件 ID → 元数据对象」的字典：

| 字段 | 说明 |
| --- | --- |
| `name` / `description` | 展示名与简介，应与类 `plugin_name` / `plugin_desc` 一致 |
| `labels` | 标签，英文逗号分隔的字符串或列表 |
| `version` | 必须等于类属性 `plugin_version` |
| `icon` | 图标文件名，必须与类 `plugin_icon` 一致，且 `icons/` 中存在同名文件（大小写敏感） |
| `author` | 作者，与 `plugin_author` 一致 |
| `level` | 用户可见级别（0–99 整数），与类 `auth_level` 一致 |
| `system_version` | 可安装的宿主版本范围，PEP 440 格式，本仓库统一 `>=3.0.0` |
| `history` | 变更日志字典，**键带 `v` 前缀**（如 `v3.0.2`），首项等于当前版本，按语义版本降序 |
| `release` | 可选，为 `true` 时走 GitHub Release ZIP 分发；默认源码目录安装 |

三处一致性由 `.github/scripts/check_plugin_versions.py` 强制：索引 `version` == 类 `plugin_version` == `history` 首项。`history` 使用带 `v` 前缀的键，Release 工作流才能用 `--arg version "v$version"` 取到发布说明。

## 4. 版本规则

- **插件更新一定要变更版本号**：只要 `plugins.v3/<id小写>/` 下任何文件发生变化（Python 源码、配置页源码、`dist/` 构建产物、插件 README 等），或 `package.v3.json` 中该插件的元数据发生变化，都必须同步递增 `version`，不允许「改了代码但版本不变」。
- 版本号按 V3 独立版本线迭代；升级时必须同步修改 `package.v3.json` 的 `version` 与 `history`、插件类的 `plugin_version`，三者必须在同一次提交内。
- 每次升级都要在 `history` 顶部新增一条记录，说明本次变更；不要再往 V3 条目里追加 V2 版本记录。
- `system_version` 只在插件确实依赖更高宿主能力时上调，不要为了「显得新」随意修改。
- `check_plugin_versions.py --check-bump <base-ref> package.v3.json` 用 `git diff <base>...HEAD -- plugins.v3` 找出被更新的插件，并强制其版本号相对 base 严格递增；PR 用 `origin/main`，push 到 `main` 用 `HEAD~1`。

## 5. 开发一个 V3 插件

1. 在 `plugins.v3/` 下按类名小写建目录，新增 `__init__.py`。
2. 继承 `_PluginBase`，实现 `init_plugin` / `get_state` / `get_api` / `get_form` / `get_page` / `stop_service`；周期任务用 `get_service()`，一次性任务用 `app.sdk.scheduler.add_plugin_once_job`。
3. 导入面优先 `app.sdk.*`：`app.sdk.config.settings`、`app.sdk.logging.logger`、`app.sdk.events.eventmanager/Event`、`app.sdk.media.*`、`app.sdk.services.*`、`app.sdk.utilities.*`、`app.sdk.network.*`。`app.core` / `app.helper` / `app.utils` / `app.log` 是兼容虚拟根，新代码不得新增依赖；媒体身份统一用 `media_source` + `media_id`。
4. UI 二选一：
   - `vuetify`：`get_form()` 返回 `(页面 JSON, 默认配置)`，详情页用 `get_page()`，仪表板用 `get_dashboard()`。
   - `vue`：`get_render_mode()` 返回 `("vue", "dist/assets")`，`get_form()` 只返回配置模型；`Config.vue` 通过 `initialConfig` 拿配置、`emit('save', config)` 交给宿主 `PUT plugin/{id}`，禁止自行 GET/PUT `plugin/{id}/config`。
5. `get_api()` 的 `path` 会被宿主拼成 `/api/v1/plugin/{plugin_id}{path}`，面向前端组件的接口声明 `auth: "bear"`，并通过组件 `api` prop 调用。
6. 在 `package.v3.json` 中补齐元数据，图标放进 `icons/`，必要时补插件 `README.md`。
7. 运行 `python .github/scripts/check_plugin_versions.py package.v3.json` 与 `python tests/run.py`。

详细规范见 `docs/Plugin_Development.md`；V2→V3 迁移要点见 `docs/V3_Plugin_Adaptation.md`；插件 API 响应契约见 `docs/V3_API_Response_Adaptation.md`；Vue 联邦组件契约以 `MoviePilot-Frontend/docs/module-federation-guide.md` 为准。

## 6. 门禁与发布

同一份版本校验脚本在三个入口复用，且都会执行「插件更新必须升版本」检查：

- `.githooks/pre-push`（本地可选启用：`git config core.hooksPath .githooks`，base 为当前分支上游）
- `.github/workflows/plugin-gate.yml`（所有指向 `main` 的 PR 与 push 到 `main`，不加 `paths` 过滤；PR 的 base 为 `origin/main`，push 为 `HEAD~1`）
- `.github/workflows/release.yml`（push 到 `main` 且 `package.v3.json` 变更，或手动触发；base 为 `HEAD~1`）

Release 工作流只处理 `package.v3.json` 中 `release: true` 的条目，从 `plugins.v3/<id小写>/` 打包，Tag 为 `<插件ID>_v<版本>`，资产为 `<id小写>_v<版本>.zip`；目录自上一个同名 Tag 无变化则跳过。当前 6 个插件均已启用 `release`，ZIP 包含 `dist/assets/`（Vue 插件必需）并排除 `__pycache__`、`node_modules` 与前端源码 `src/`。

宿主的「版本历史」弹窗把索引 `history` 与 GitHub Release 列表合并显示：只有存在对应 Release 的版本才会出现「安装」按钮，「当前」标记由后端对比本地 `plugin_version` 与 Release 版本得出。因此新增版本后必须让 Release 工作流成功发布，否则该版本只有说明文字、没有安装按钮。

历史版本补发：在 GitHub Actions 手动运行 `Plugin Release`，勾选 `backfill`（可设 `max_per_plugin`，默认每插件 10 个）。脚本 `.github/scripts/backfill_releases.sh` 会遍历 `history`，从「索引中该插件版本等于目标版本」的 git 提交取代码快照打包；找不到 V3 快照的记录（如沿用 V2 说明）自动跳过，已存在的 Release 不会重建。该步骤默认不自动执行，避免一次性创建大量 Release。

## 7. 测试

- `tests/ci/`：仓库级契约测试（版本门禁、工作流、V3 元数据一致性）。
- `tests/v3/<plugin_id>/`：插件级契约测试，按插件 ID 建目录。
- 契约测试是静态校验（JSON / AST），不需要 MoviePilot 运行时；`tests/_bootstrap.py` 只在需要真实后端时按需加载，后端路径由 `MOVIEPILOT_BACKEND_PATH` 或同级 `MoviePilot/` 推导。
- 运行方式：`python tests/run.py`，或 `python -m pytest tests`。

## 8. 文档索引

| 想做什么 | 看哪里 |
| --- | --- |
| 维护仓库、改索引、发版本 | 本文档 |
| 开发插件、查扩展点 | `docs/Plugin_Development.md` |
| V2 代码迁移到 V3 | `docs/V3_Plugin_Adaptation.md` |
| 插件 API / 远程组件响应适配 | `docs/V3_API_Response_Adaptation.md` |
| 按场景查用法 | `docs/FAQ.md` 与 `docs/faq/`（22 篇） |
| Vue 联邦组件契约 | `MoviePilot-Frontend/docs/module-federation-guide.md` |
