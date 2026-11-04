# 插件仓单测（V3）

测试统一放在仓库根 `tests/` 下，**不放在插件目录内**——插件的本地同步与市场下发按整目录拷贝（`shutil.copytree`），插件目录内的测试会被一并下发到运行时副本。

## 目录结构

```
tests/
├─ helpers.py                     # 共享的 V3 索引/源码静态契约检查
├─ conftest.py                    # pytest 引导，默认不加载后端
├─ _bootstrap.py                  # 可选：按需定位 V3 后端并注入 plugins.v3/
├─ run.py                         # 全量入口
├─ ci/                            # 仓库级门禁与工作流契约测试
└─ v3/<plugin_id>/test_plugin.py  # 插件级契约测试，按插件 ID 建目录
```

## 运行

```bash
python tests/run.py
# 或
python -m pytest tests
```

契约测试是纯静态校验（JSON / AST / 文本），不需要 MoviePilot 运行时，也不访问网络。

需要加载插件运行时（例如调用 `init_plugin`）时，把后端放到插件仓同级目录 `MoviePilot/`，或设置 `MOVIEPILOT_BACKEND_PATH`，并启用：

```bash
MOVIEPILOT_PLUGIN_RUNTIME_TESTS=1 python -m pytest tests/v3
```

后端需包含 `app/testing/bootstrap.py`（MoviePilot V3）；引导逻辑统一复用主程序的 `prepare_v3_backend`。

## 新增用例

1. 插件级用例放 `tests/v3/<plugin_id>/test_plugin.py`，文件名使用 `test_*.py`。
2. 使用 pytest 风格（普通函数 + `assert`），不要新增 `unittest.TestCase` 或 `if __name__ == "__main__"` 入口。
3. 优先复用 `tests/helpers.py` 的 `assert_plugin_contract()`，只测纯逻辑或静态契约；需要真实运行时时才启用 `_bootstrap.py`。
