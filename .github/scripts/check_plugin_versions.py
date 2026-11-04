#!/usr/bin/env python3
"""校验 V3 插件市场契约。

Release 工作流依赖 package.v3.json 生成 tag、资产名与发布说明；若索引与插件源码
不同步，运行时会继续展示旧版本或取不到发布说明。这里在打包前失败退出。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=SyntaxWarning)

PACKAGE_PLUGIN_DIRS = {"package.v3.json": Path("plugins.v3")}
PLUGIN_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


def _load_package(path: Path) -> dict:
    """读取 package 文件；文件不存在时返回空字典。"""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _plugin_dir(package_file: Path, plugin_id: str) -> Path | None:
    """按 package 文件定位 V3 插件目录。"""
    base_dir = PACKAGE_PLUGIN_DIRS.get(package_file.name, Path("plugins.v3"))
    candidate = package_file.parent / base_dir / plugin_id.lower()
    return candidate if candidate.is_dir() else None


def _semantic_version(value: object) -> tuple[int, ...] | None:
    """将版本号解析为数字元组，兼容可选的 ``v`` 前缀。"""
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", str(value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _compare_versions(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    """按语义版本数字段比较两个版本，缺失的小版本段按零处理。"""
    width = max(len(left), len(right), 3)
    normalized_left = left + (0,) * (width - len(left))
    normalized_right = right + (0,) * (width - len(right))
    return (normalized_left > normalized_right) - (normalized_left < normalized_right)


def _plugin_class_meta(init_file: Path) -> tuple[str | None, dict]:
    """从 __init__.py 中提取主类名与其类级字面量属性。"""
    tree = ast.parse(init_file.read_text(encoding="utf-8"), filename=str(init_file))
    attributes: dict = {}
    for class_node in (node for node in tree.body if isinstance(node, ast.ClassDef)):
        for node in class_node.body:
            value_node = None
            name = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                value_node = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                value_node = node.value
            if name and isinstance(value_node, ast.Constant) and isinstance(value_node.value, (str, int, bool)):
                attributes[name] = value_node.value
        return class_node.name, attributes
    return None, attributes


def _check_history(path: Path, plugin_id: str, version: str, history: object) -> list[str]:
    """校验变更日志格式、首项版本与降序排列。"""
    prefix = f"{path}: {plugin_id}"
    if not isinstance(history, dict) or not history:
        return [f"{prefix} 缺少非空 history"]
    errors: list[str] = []
    keys = list(history)
    parsed = [_semantic_version(key) for key in keys]
    for key, item in zip(keys, parsed):
        if not isinstance(key, str) or not key.startswith("v"):
            errors.append(f"{prefix} history 键 {key} 必须以 v 开头（如 v3.0.2）")
        if item is None:
            errors.append(f"{prefix} history 包含非法版本 {key}")
        if not isinstance(history[key], str) or not history[key].strip():
            errors.append(f"{prefix} history[{key}] 必须是非空变更说明")
    current = _semantic_version(version)
    if current is None:
        errors.append(f"{prefix} 当前版本 {version or '<空>'} 不是合法语义版本")
    elif parsed[0] is None or _compare_versions(parsed[0], current) != 0:
        errors.append(f"{prefix} history 首项 {keys[0]} 与当前版本 {version} 不一致")
    for previous_key, previous, current_key, following in zip(keys, parsed, keys[1:], parsed[1:]):
        if previous and following and _compare_versions(previous, following) < 0:
            errors.append(f"{prefix} history 未按语义版本降序排列：{previous_key} 在 {current_key} 之前")
    return errors


def check_package(path: Path) -> list[str]:
    """校验单个 V3 package 文件，返回所有错误文本。"""
    errors: list[str] = []
    package = _load_package(path)
    for plugin_id, meta in package.items():
        prefix = f"{path}: {plugin_id}"
        if not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            errors.append(f"{prefix} 插件 ID 不合法（应为字母开头的 ASCII 字母数字下划线）")
        if not isinstance(meta, dict):
            errors.append(f"{prefix} 元数据必须是对象")
            continue

        version = str(meta.get("version") or "").strip()
        system_version = meta.get("system_version")
        if not isinstance(system_version, str) or not system_version.strip():
            errors.append(f"{prefix} 缺少 system_version")
        level = meta.get("level")
        if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 99:
            errors.append(f"{prefix} level 必须是 0–99 的整数")
        icon = meta.get("icon")
        if not isinstance(icon, str) or not icon.strip():
            errors.append(f"{prefix} 缺少 icon")
        elif not icon.startswith(("http://", "https://")):
            if not (path.parent / "icons" / icon).is_file():
                errors.append(f"{prefix} 图标文件 icons/{icon} 不存在（注意大小写）")

        errors.extend(_check_history(path, plugin_id, version, meta.get("history")))

        plugin_dir = _plugin_dir(path, plugin_id)
        if not plugin_dir:
            errors.append(f"{prefix} 缺少插件目录 {path.parent / 'plugins.v3' / plugin_id.lower()}")
            continue
        init_file = plugin_dir / "__init__.py"
        if not init_file.exists():
            errors.append(f"{prefix} 缺少 {init_file}")
            continue
        class_name, attributes = _plugin_class_meta(init_file)
        if class_name != plugin_id:
            errors.append(f"{prefix} 主类名 {class_name} 与插件 ID 不一致")
        source_version = attributes.get("plugin_version")
        if not isinstance(source_version, str) or not source_version:
            errors.append(f"{prefix} 未在 {init_file} 中声明类级 plugin_version")
        elif source_version != version:
            errors.append(f"{prefix} 版本不一致，package={version}, plugin_version={source_version}")
        if isinstance(icon, str) and "plugin_icon" in attributes and attributes["plugin_icon"] != icon:
            errors.append(f"{prefix} icon 与类 plugin_icon={attributes['plugin_icon']} 不一致")
        if isinstance(level, int) and "auth_level" in attributes and attributes["auth_level"] != level:
            errors.append(f"{prefix} level 与类 auth_level={attributes['auth_level']} 不一致")
        if "plugin_author" in attributes and attributes["plugin_author"] != meta.get("author"):
            errors.append(f"{prefix} author 与类 plugin_author={attributes['plugin_author']} 不一致")

        source_text = init_file.read_text(encoding="utf-8")
        if 'return "vue"' in source_text or "return 'vue'" in source_text:
            if not (plugin_dir / "dist" / "assets" / "remoteEntry.js").is_file():
                errors.append(f"{prefix} Vue 模式缺少 dist/assets/remoteEntry.js")
    return errors


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """执行只读 git 命令，显式按 UTF-8 解码以兼容 Windows 中文环境。"""
    return subprocess.run(
        ["git", *args], text=True, capture_output=True, check=False,
        encoding="utf-8", errors="replace",
    )


def check_version_bump(base_ref: str, path: Path) -> list[str]:
    """插件有任何更新时版本号必须严格递增。

    PR 场景传 ``origin/main``，push 到 main 场景传 ``HEAD~1``。三点 diff 只统计
    本次提交链引入的变更；除 ``plugins.v3/`` 目录外，索引元数据变化也算插件更新。
    """
    diff = _git("diff", "--name-only", f"{base_ref}...HEAD", "--", "plugins.v3")
    if diff.returncode != 0:
        return [f"无法比较 {base_ref}...HEAD：{(diff.stderr or '').strip()}"]
    changed_dirs = set()
    for line in (diff.stdout or "").splitlines():
        parts = line.strip().split("/")
        if len(parts) >= 2 and parts[0] == "plugins.v3":
            changed_dirs.add(parts[1].lower())

    shown = _git("show", f"{base_ref}:package.v3.json")
    if shown.returncode != 0:
        return [f"无法读取 {base_ref}:package.v3.json：{(shown.stderr or '').strip()}"]
    raw = shown.stdout or ""
    previous_index = json.loads(raw) if raw.strip() else {}
    current_index = _load_package(path)
    changed_ids = {
        plugin_id.lower()
        for plugin_id, meta in current_index.items()
        if isinstance(previous_index.get(plugin_id), dict) and previous_index[plugin_id] != meta
    }
    targets = changed_dirs | changed_ids
    if not targets:
        return []

    errors: list[str] = []
    for plugin_id, meta in current_index.items():
        if plugin_id.lower() not in targets:
            continue
        previous = previous_index.get(plugin_id)
        if not isinstance(previous, dict):
            continue  # 新增插件无需递增
        previous_version = previous.get("version")
        current_version = meta.get("version")
        left = _semantic_version(previous_version)
        right = _semantic_version(current_version)
        if left is None or right is None or _compare_versions(right, left) <= 0:
            errors.append(
                f"{plugin_id} 插件有更新，但版本未递增"
                f"（{previous_version} → {current_version}）；插件更新必须变更版本号"
            )
    return errors


def main() -> int:
    """命令入口：静态契约 + 可选的版本递增检查，全部通过返回 0。"""
    args = sys.argv[1:]
    bump_ref = None
    if "--check-bump" in args:
        position = args.index("--check-bump")
        if position + 1 >= len(args):
            print("插件版本门禁失败：\n- --check-bump 缺少 base ref 参数")
            return 1
        bump_ref = args[position + 1]
        args = args[:position] + args[position + 2:]

    package_files = [Path(arg) for arg in args] or [Path("package.v3.json")]
    errors: list[str] = []
    for package_file in package_files:
        errors.extend(check_package(package_file))
    if bump_ref:
        errors.extend(check_version_bump(bump_ref, package_files[0]))
    if errors:
        print("插件版本门禁失败：")
        for error in errors:
            print(f"- {error}")
        return 1
    print("插件版本门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
