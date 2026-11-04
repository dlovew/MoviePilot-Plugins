"""DownloadSiteTagModdlovew 插件契约测试。"""
from tests.helpers import assert_plugin_contract

PLUGIN_ID = "DownloadSiteTagModdlovew"


def test_plugin_contract() -> None:
    """插件目录、主类、元数据、导入面与 Vue 产物均符合 V3 契约。"""
    assert_plugin_contract(PLUGIN_ID)
