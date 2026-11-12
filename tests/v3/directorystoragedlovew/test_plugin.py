"""DirectoryStoragedlovew 插件的静态契约测试。"""
import ast

from tests.helpers import REPO_ROOT, assert_plugin_contract

PLUGIN_ID = "DirectoryStoragedlovew"
INIT_FILE = REPO_ROOT / "plugins.v3" / "directorystoragedlovew" / "__init__.py"


def test_plugin_contract():
    assert_plugin_contract(PLUGIN_ID)


def test_dashboard_hooks_present():
    """仪表盘小组件依赖这几个钩子，避免后续重构时误删。"""
    tree = ast.parse(INIT_FILE.read_text(encoding="utf-8"))
    plugin_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    methods = {
        node.name for node in plugin_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {"get_dashboard", "get_dashboard_meta", "get_form", "get_page"} <= methods
