# MoviePilot-Plugins

**MoviePilot V3 自用插件仓库**

![兼容版本](https://img.shields.io/badge/MoviePilot-V3-8b949e?style=flat-square)
![插件数量](https://img.shields.io/badge/plugins-4-8b949e?style=flat-square)
![作者](https://img.shields.io/badge/author-dlovew-8b949e?style=flat-square)
[![最近提交](https://img.shields.io/github/last-commit/dlovew/MoviePilot-Plugins?style=flat-square&color=8b949e)](https://github.com/dlovew/MoviePilot-Plugins/commits/main)

---

纯个人使用导向的 MoviePilot V3 插件集合。自己写、自己改、自己用，主要是为了解决我自己部署环境里遇到的实际痛点（下载标签、订阅填充、番剧订阅、混合种子修复）。

所有插件都基于官方或社区插件的思路魔改而来，保留了明确的上游来源说明；命名统一加 `-dlovew` 后缀以和原版区分，但**插件 ID 保持不变**，方便从其他市场平滑迁移或升级。

> ⚠️ 仓库定位就是自用，不保证通用性、不保证适配你的环境、不接受定制需求。代码开源仅供有相似需求的人参考，出问题请先看日志自己排查。

## 插件清单

| 图标 | 插件名 | 说明 | 上游来源 |
| :---: | --- | --- | :---: |
| 🏷️ | 下载任务分类与标签魔改VUE版 -dlovew | 按站点 / 分类为下载任务自动设置 qBittorrent 标签与二级分类（带独立 Vue 配置页）。 | 社区下载标签插件魔改 |
| 📺 | 订阅规则自动填充魔改版 -dlovew | 基于 Seed680 魔改版，按剧集分组规则自动填充订阅的季 / 集信息并优化数据获取。 | SubscribeGroupMod (Seed680) |
| 📡 | 自定义订阅番剧魔改版 -dlovew | 监听 RSS 自动订阅番剧；按流媒体平台分流：IQ+2160P 与 LINETV 走强订阅（带站点 / 制作组 / 特效 / 分辨率精细 include），其余仅通知。 | 官方 rssubscribe 2.1 |
| 🔧 | qBittorrent 混合种子修复 -dlovew | 定时扫描 qBittorrent 中因 MoviePilot 拆包只下载合集最后一集而处于混合状态的种子，将其全部文件优先级恢复为正常。 | 原创自用 |

> 命名规则：在原版插件名后追加 `-dlovew` 后缀，作者统一为 `dlovew`，插件 ID 维持原版不变，确保升级无碍。

## 安装

在 MoviePilot 的 `PLUGIN_MARKET` 中加入本仓库地址：

```text
https://github.com/dlovew/MoviePilot-Plugins
```

> 本仓库的插件以 V3 为主（目录 `plugins.v3/` + 索引 `package.v3.json`），`plugins.v2/` 与 `package.v2.json` 仅作为旧版本残留保留，不再主动维护。请确保你的 MoviePilot 已升级到 V3（`>=3.0.0`）。
> 如果你在国内访问 GitHub 受 `GITHUB_TOKEN` 限流影响，可配置代理或自托管的镜像源。

## 更新

插件市场内直接点击「更新」即可。每个插件的变更日志写在 `package.v3.json` 的 `history` 字段里，安装后也能在插件详情页看到。

## 注意事项

- 本仓库**以自用为主**，插件行为按我个人环境调校，不保证在你的环境开箱即用。
- 涉及写文件、改配置、操作下载器的动作，默认倾向「只报告 / 最小改动」，避免误伤你的数据。
- 排错时请先提供 MoviePilot 主程序日志路径与插件日志，再提 Issue 或自行查阅对应插件目录下的 `README.md`。

## 许可

个人学习 / 自用目的开源。基于官方或社区插件魔改的部分，版权归原上游作者所有；我个人的改动部分以仓库 `LICENSE` 为准。未经允许的二次分发请保留原作者与上游来源说明。
