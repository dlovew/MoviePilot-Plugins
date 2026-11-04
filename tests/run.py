"""V3 插件仓全量单测入口：一次会话运行 tests/ 下全部用例，命令行参数透传给 pytest。

本仓库只维护 V3 插件，不存在 v1/v2 同名插件包冲突，无需再分代启动子进程。
"""
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "pytest", "tests", *sys.argv[1:]],
            cwd=str(_REPO_ROOT),
        )
    )
