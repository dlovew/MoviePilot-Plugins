"""V3 插件静态契约检查的共享实现。

不依赖 MoviePilot 运行时：索引用 json 读取，插件源码用 ast 解析，适合在 CI 中快速回归。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = REPO_ROOT / "package.v3.json"
PLUGINS_DIR = REPO_ROOT / "plugins.v3"
ICONS_DIR = REPO_ROOT / "icons"

# V2 兼容虚拟根与已迁移的旧模块路径，V3 插件不得再新增依赖。
BANNED_IMPORT_PREFIXES = (
    "app.core.",
    "app.helper.",
    "app.utils.",
    "app.log",
    "app.db.downloadhistory_oper",
    "app.db.systemconfig_oper",
    "app.modules.qbittorrent",
)


def load_index() -> dict:
    """读取 V3 市场索引。"""
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def plugin_ids() -> list[str]:
    """返回索引中全部插件 ID。"""
    return list(load_index())


def plugin_contract_errors(plugin_id: str) -> list[str]:
    """校验单个插件的目录、主类、元数据与导入面，返回错误文本列表。"""
    errors: list[str] = []
    meta = load_index().get(plugin_id)
    if not isinstance(meta, dict):
        return [f"{plugin_id}: package.v3.json 中不存在该插件"]

    plugin_dir = PLUGINS_DIR / plugin_id.lower()
    if not plugin_dir.is_dir():
        return [f"{plugin_id}: 缺少插件目录 {plugin_dir}"]
    init_file = plugin_dir / "__init__.py"
    if not init_file.is_file():
        return [f"{plugin_id}: 缺少 {init_file}"]

    source = init_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(init_file))
    except SyntaxError as error:
        return [f"{plugin_id}: __init__.py 语法错误 {error}"]

    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if not classes:
        errors.append(f"{plugin_id}: __init__.py 中未定义插件主类")
    else:
        main_class = classes[0]
        if main_class.name != plugin_id:
            errors.append(f"{plugin_id}: 主类名 {main_class.name} 与插件 ID 不一致")
        attributes: dict = {}
        for node in main_class.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if isinstance(node.value, ast.Constant):
                    attributes[node.targets[0].id] = node.value.value
        if attributes.get("plugin_version") != meta.get("version"):
            errors.append(
                f"{plugin_id}: plugin_version={attributes.get('plugin_version')} 与索引 version={meta.get('version')} 不一致"
            )
        if attributes.get("plugin_icon") != meta.get("icon"):
            errors.append(f"{plugin_id}: plugin_icon 与索引 icon 不一致")
        if isinstance(meta.get("level"), int) and attributes.get("auth_level") != meta.get("level"):
            errors.append(f"{plugin_id}: auth_level 与索引 level 不一致")
        if attributes.get("plugin_author") != meta.get("author"):
            errors.append(f"{plugin_id}: plugin_author 与索引 author 不一致")

    icon = meta.get("icon")
    if isinstance(icon, str) and not icon.startswith(("http://", "https://")):
        if not (ICONS_DIR / icon).is_file():
            errors.append(f"{plugin_id}: 图标文件 icons/{icon} 不存在")

    if not isinstance(meta.get("system_version"), str) or not meta["system_version"].strip():
        errors.append(f"{plugin_id}: 缺少 system_version")

    for node in ast.walk(tree):
        module = None
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
        elif isinstance(node, ast.Import):
            module = ", ".join(alias.name for alias in node.names)
        if module and any(module.startswith(prefix) for prefix in BANNED_IMPORT_PREFIXES):
            errors.append(f"{plugin_id}: 仍在使用 V2 导入路径 {module}")

    if 'return "vue"' in source or "return 'vue'" in source:
        remote_entry = plugin_dir / "dist" / "assets" / "remoteEntry.js"
        if not remote_entry.is_file():
            errors.append(f"{plugin_id}: Vue 模式缺少 dist/assets/remoteEntry.js")
        else:
            # V3 宿主在 vue 模式下：设置页加载 ./Config，数据页加载 ./Page，缺一即报错
            remote_text = remote_entry.read_text(encoding="utf-8")
            for expose in ("./Config", "./Page"):
                if f'"{expose}"' not in remote_text and f"'{expose}'" not in remote_text:
                    errors.append(f"{plugin_id}: dist/assets/remoteEntry.js 未暴露 {expose}")
        if not (plugin_dir / "src" / "components" / "Config.vue").is_file():
            errors.append(f"{plugin_id}: Vue 模式缺少可维护的 src/components/Config.vue 源码")
        if not (plugin_dir / "src" / "components" / "Page.vue").is_file():
            errors.append(f"{plugin_id}: Vue 模式缺少可维护的 src/components/Page.vue 源码")
    return errors


def assert_plugin_contract(plugin_id: str) -> None:
    """断言单个插件满足全部静态契约。"""
    errors = plugin_contract_errors(plugin_id)
    assert not errors, "\n".join(errors)
