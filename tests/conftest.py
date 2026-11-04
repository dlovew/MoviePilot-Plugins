"""pytest 全局引导：契约测试默认纯静态，可选加载 V3 运行时。

设置 ``MOVIEPILOT_PLUGIN_RUNTIME_TESTS=1`` 且后端可用时，才注入 ``plugins.v3/``；
这样 GitHub Actions 与本地无后端环境也能直接运行全部契约测试。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def pytest_configure(config) -> None:
    """按需准备 V3 后端运行时，静态契约测试不触发任何后端导入。"""
    if os.environ.get("MOVIEPILOT_PLUGIN_RUNTIME_TESTS") != "1":
        return
    from tests._bootstrap import prepare_v3_backend

    prepare_v3_backend()
