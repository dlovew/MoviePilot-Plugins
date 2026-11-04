"""SubscribeGroupModdlovew 插件契约测试。"""
from tests.helpers import assert_plugin_contract

PLUGIN_ID = "SubscribeGroupModdlovew"


def test_plugin_contract() -> None:
    """插件目录、主类、元数据与导入面均符合 V3 契约。"""
    assert_plugin_contract(PLUGIN_ID)
