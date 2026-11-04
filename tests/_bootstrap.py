"""可选的 V3 运行时引导。

仓库契约测试是纯静态校验，不需要 MoviePilot 后端。只有确实要加载插件运行时（例如
调用 ``init_plugin``）时，才按需调用 :func:`prepare_v3_backend`；后端路径优先取环境变量
``MOVIEPILOT_BACKEND_PATH``，否则按插件仓同级目录 ``MoviePilot`` 推导。
"""
from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_PLUGINS_REPO = _TESTS_DIR.parent


def backend_path() -> Path:
    """定位 MoviePilot V3 后端根目录，找不到时抛出可诊断的错误。"""
    candidates = []
    env = os.environ.get("MOVIEPILOT_BACKEND_PATH")
    if env:
        candidates.append(Path(env).expanduser())
    candidates.extend([_PLUGINS_REPO.parent / "MoviePilot", _PLUGINS_REPO.parent / "MoviePilot-3"])
    for path in candidates:
        if (path / "app" / "testing" / "bootstrap.py").is_file():
            return path
    raise RuntimeError(
        "未找到 MoviePilot V3 后端（app/testing/bootstrap.py 不存在）。"
        "请设置环境变量 MOVIEPILOT_BACKEND_PATH。已尝试: "
        f"{[str(path) for path in candidates]}"
    )


def prepare_v3_backend() -> None:
    """隔离配置目录、建表并把 ``plugins.v3/`` 注入插件命名空间。"""
    path = backend_path()
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    bootstrap = import_module("app.testing.bootstrap")
    bootstrap.prepare_v3_backend(_PLUGINS_REPO)


def block_real_network():
    """按需加载主程序共享的网络守卫（导入即注册 autouse fixture）。"""
    path = backend_path()
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    return import_module("app.testing.network_guard").block_real_network
