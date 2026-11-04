"""验证 V3 版本门禁、工作流、仓库清理结果与插件静态契约。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from tests.helpers import INDEX_FILE, REPO_ROOT, assert_plugin_contract, load_index, plugin_ids

CHECKER = REPO_ROOT / ".github/scripts/check_plugin_versions.py"
PRE_PUSH = REPO_ROOT / ".githooks/pre-push"
PR_WORKFLOW = REPO_ROOT / ".github/workflows/plugin-gate.yml"
RELEASE_WORKFLOW = REPO_ROOT / ".github/workflows/release.yml"


def _write_fixture(repo: Path, *, package_version: str = "3.0.0", source_version: str = "3.0.0",
                   history_key: str = "v3.0.0", with_dir: bool = True,
                   source_body: str | None = None, meta_override: dict | None = None) -> None:
    """构造最小 V3 插件仓，隔离验证 checker 的退出码与报错。"""
    if with_dir:
        plugin_dir = repo / "plugins.v3/example"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "__init__.py").write_text(
            source_body or (
                "class Example:\n"
                f'    plugin_version = "{source_version}"\n'
                '    plugin_icon = "https://example.com/icon.png"\n'
                "    auth_level = 1\n"
                '    plugin_author = "dlovew"\n'
            ),
            encoding="utf-8",
        )
    meta = {
        "name": "示例插件",
        "description": "示例",
        "labels": "示例",
        "version": package_version,
        "icon": "https://example.com/icon.png",
        "author": "dlovew",
        "level": 1,
        "system_version": ">=3.0.0",
        "history": {history_key: "初始版本"},
    }
    if meta_override:
        meta.update(meta_override)
    (repo / "package.v3.json").write_text(json.dumps({"Example": meta}, ensure_ascii=False), encoding="utf-8")


def _run_checker(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """运行仓库真实的版本门禁脚本。"""
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def test_current_repository_passes_version_gate() -> None:
    """启用 Required Check 前，真实 main 基线必须通过。"""
    result = _run_checker(REPO_ROOT, "package.v3.json")
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_rejects_mismatched_versions(tmp_path: Path) -> None:
    """索引与源码版本不一致时必须失败。"""
    _write_fixture(tmp_path, source_version="2.9.9")
    result = _run_checker(tmp_path, "package.v3.json")
    assert result.returncode == 1
    assert "版本不一致" in result.stdout


def test_checker_reports_missing_plugin_dir(tmp_path: Path) -> None:
    """缺少插件目录时失败，避免发布项被静默跳过。"""
    _write_fixture(tmp_path, with_dir=False)
    result = _run_checker(tmp_path, "package.v3.json")
    assert result.returncode == 1
    assert "缺少插件目录" in result.stdout
    # Windows 上 Path 输出反斜杠，统一归一化后断言
    assert "plugins.v3/example" in result.stdout.replace("\\", "/")


def test_checker_rejects_history_without_v_prefix(tmp_path: Path) -> None:
    """history 键必须带 v 前缀，否则 Release 取不到发布说明。"""
    _write_fixture(tmp_path, history_key="3.0.0")
    result = _run_checker(tmp_path, "package.v3.json")
    assert result.returncode == 1
    assert "必须以 v 开头" in result.stdout


def test_checker_rejects_function_scoped_version(tmp_path: Path) -> None:
    """只接受类级 plugin_version，避免局部变量被误识别。"""
    _write_fixture(
        tmp_path,
        source_body="def helper():\n    plugin_version = '3.0.0'\n    return plugin_version\n",
    )
    result = _run_checker(tmp_path, "package.v3.json")
    assert result.returncode == 1
    assert "类级 plugin_version" in result.stdout


def test_checker_rejects_missing_system_version(tmp_path: Path) -> None:
    """V3 插件必须声明宿主版本范围。"""
    _write_fixture(tmp_path, meta_override={"system_version": None})
    result = _run_checker(tmp_path, "package.v3.json")
    assert result.returncode == 1
    assert "system_version" in result.stdout


def test_checker_rejects_level_mismatch(tmp_path: Path) -> None:
    """索引 level 与类 auth_level 必须一致。"""
    _write_fixture(tmp_path, meta_override={"level": 2})
    result = _run_checker(tmp_path, "package.v3.json")
    assert result.returncode == 1
    assert "auth_level" in result.stdout


def test_gate_hook_and_workflows_are_v3_only() -> None:
    """三个门禁入口必须一致地校验 package.v3.json，且不再引用 V2 索引。"""
    for path in (PRE_PUSH, PR_WORKFLOW, RELEASE_WORKFLOW):
        content = path.read_text(encoding="utf-8")
        assert "package.v3.json" in content, path
        assert "package.v2.json" not in content, path
    assert "plugins.v3/" in RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in PR_WORKFLOW.read_text(encoding="utf-8")
    assert "paths:" not in PR_WORKFLOW.read_text(encoding="utf-8")


def test_no_v2_assets_remain() -> None:
    """仓库不应残留任何 V2 插件资产。"""
    for relative in (
        "plugins.v2",
        "package.v2.json",
        "docs/V2_Plugin_Development.md",
        "tests/v1",
        "tests/v2",
    ):
        assert not (REPO_ROOT / relative).exists(), relative
    for text_file in (REPO_ROOT / "README.md", REPO_ROOT / "docs/Repository_Guide.md"):
        assert "package.v2.json" not in text_file.read_text(encoding="utf-8"), text_file
    legacy_index = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    assert legacy_index == {}


def test_all_indexed_plugins_satisfy_contract() -> None:
    """索引里的每个插件都必须通过静态契约检查。"""
    assert plugin_ids(), "package.v3.json 不能为空"
    for plugin_id in plugin_ids():
        assert_plugin_contract(plugin_id)


def test_index_history_is_prefixed_and_ordered() -> None:
    """history 键带 v 前缀、首项为当前版本且按语义版本降序。"""
    def numeric(key: str) -> tuple[int, ...]:
        return tuple(int(part) for part in key.lstrip("v").split("."))

    for plugin_id, meta in load_index().items():
        history = meta.get("history")
        assert isinstance(history, dict) and history, plugin_id
        keys = list(history)
        assert all(key.startswith("v") for key in keys), plugin_id
        assert keys[0] == f"v{meta['version']}", plugin_id
        assert all(numeric(key) >= numeric(next_key) for key, next_key in zip(keys, keys[1:])), plugin_id
        assert INDEX_FILE.is_file()


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """在临时仓库执行 git 命令，内联身份以免改动全局或仓库配置。"""
    return subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.name=contract-test",
            "-c", "user.email=contract-test@example.com",
            *args,
        ],
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def _init_bump_repo(repo: Path, version: str = "3.0.0") -> None:
    """构造一个合规的 V3 插件仓并提交基线。"""
    _write_fixture(repo, package_version=version, source_version=version, history_key=f"v{version}")
    scripts = repo / ".github/scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(CHECKER, scripts / CHECKER.name)
    _run_git(repo, "init", "-q")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", "baseline")


def _commit(repo: Path, message: str) -> None:
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", message)


def _bump_check(repo: Path, base: str = "HEAD~1") -> subprocess.CompletedProcess[str]:
    """在临时仓库中运行真实版本门禁的版本递增检查。"""
    return subprocess.run(
        [
            sys.executable,
            str(repo / ".github/scripts/check_plugin_versions.py"),
            "--check-bump", base, "package.v3.json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def test_version_bump_required_when_plugin_files_change(tmp_path: Path) -> None:
    """改了插件代码但没升版本，门禁必须失败。"""
    repo = tmp_path / "bump-required"
    repo.mkdir()
    _init_bump_repo(repo)
    init_file = repo / "plugins.v3/example/__init__.py"
    init_file.write_text(
        init_file.read_text(encoding="utf-8") + "\n# 更新插件逻辑，但忘记升版本\n",
        encoding="utf-8",
    )
    _commit(repo, "change plugin without version bump")
    result = _bump_check(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "插件更新必须变更版本号" in result.stdout


def test_version_bump_passes_when_version_increases(tmp_path: Path) -> None:
    """同步升版本后，门禁通过。"""
    repo = tmp_path / "bump-ok"
    repo.mkdir()
    _init_bump_repo(repo)
    init_file = repo / "plugins.v3/example/__init__.py"
    init_file.write_text(
        init_file.read_text(encoding="utf-8").replace('plugin_version = "3.0.0"', 'plugin_version = "3.0.1"')
        + "\n# 更新插件逻辑\n",
        encoding="utf-8",
    )
    meta = json.loads((repo / "package.v3.json").read_text(encoding="utf-8"))
    meta["Example"]["version"] = "3.0.1"
    meta["Example"]["history"] = {"v3.0.1": "更新插件逻辑", "v3.0.0": "初始版本"}
    (repo / "package.v3.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    _commit(repo, "change plugin with version bump")
    result = _bump_check(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_bump_needed_for_non_plugin_changes(tmp_path: Path) -> None:
    """只改文档等仓库级文件时不要求升版本。"""
    repo = tmp_path / "docs-only"
    repo.mkdir()
    _init_bump_repo(repo)
    (repo / "docs").mkdir()
    (repo / "docs/guide.md").write_text("文档更新\n", encoding="utf-8")
    _commit(repo, "docs only")
    result = _bump_check(repo)
    assert result.returncode == 0, result.stdout + result.stderr
