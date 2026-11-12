"""目录存储插件纯逻辑的单元测试（按文件路径加载，无需宿主运行时）。"""
from __future__ import annotations

import importlib.util

import pytest

from tests.helpers import REPO_ROOT

MODULE_PATH = REPO_ROOT / "plugins.v3" / "directorystoragedlovew" / "storage_logic.py"


@pytest.fixture(scope="module")
def logic():
    spec = importlib.util.spec_from_file_location("storage_logic_under_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_format_size(logic):
    assert logic.format_size(0) == '0 B'
    assert logic.format_size(-1) == '0 B'
    assert logic.format_size('bad') == '0 B'
    assert logic.format_size(512) == '512 B'
    gib = 1024 ** 3
    assert logic.format_size(gib) == '1.00 GB'
    assert logic.format_size(1.23 * gib) == '1.23 GB'
    assert logic.format_size(1024 ** 4) == '1.00 TB'


def test_usage_percent_and_color(logic):
    assert logic.usage_percent(100, 40) == 60.0
    assert logic.usage_percent(100, 120) == 0.0
    assert logic.usage_percent(0, 0) == 0.0
    assert logic.usage_percent('bad', 1) == 0.0
    assert logic.progress_color(50) == '#1E88E5'
    assert logic.progress_color(90) == '#FB8C00'
    assert logic.progress_color(96) == '#E53935'


def test_extract_paths(logic):
    confs = [
        {'name': '动画', 'storage': 'local', 'library_storage': 'local',
         'download_path': '/vol1/download', 'library_path': '/vol1/media'},
        {'name': '远程', 'storage': 'alist', 'library_storage': 'alist',
         'download_path': '/remote/dl', 'library_path': '/remote/lib'},
        {'name': '动画2', 'storage': 'local', 'library_storage': 'local',
         'download_path': '/vol1/download', 'library_path': ''},
    ]
    items = logic.extract_paths(confs)
    assert [(item['label'], item['path']) for item in items] == [
        ('动画 · 下载', '/vol1/download'),
        ('动画 · 媒体库', '/vol1/media'),
    ]
    all_items = logic.extract_paths(confs, local_only=False)
    assert len(all_items) == 4
    only_library = logic.extract_paths(
        confs, include_download=False, local_only=False)
    assert all(item['kind'] == 'library' for item in only_library)


def test_extract_paths_custom(logic):
    custom = '# 注释\n卷3|/vol3\n/vol4\n卷3|/vol3'
    items = logic.extract_paths([], custom)
    assert [(item['label'], item['path'], item['kind']) for item in items] == [
        ('卷3', '/vol3', 'custom'),
        ('/vol4', '/vol4', 'custom'),
    ]


def test_build_rows(logic):
    items = [
        {'label': 'A', 'path': '/a', 'kind': 'download'},
        {'label': 'B', 'path': '/b', 'kind': 'library'},
        {'label': 'C', 'path': '/missing', 'kind': 'custom'},
    ]
    gib = 1024 ** 3

    def usage(path):
        if path == '/missing':
            return 0, 0, 'disk0'
        if path == '/a':
            return 10 * gib, 4 * gib, 'disk1'
        return 10 * gib, 4 * gib, 'disk1'

    rows = logic.build_rows(items, usage)
    assert len(rows) == 2
    assert rows[0]['used'] == 6 * gib
    assert rows[0]['percent'] == 60.0
    assert rows[0]['color'] == '#1E88E5'

    merged = logic.build_rows(items, usage, merge_by_disk=True)
    assert len(merged) == 1
    assert merged[0]['label'] == 'A / B'
    assert '/a' in merged[0]['path'] and '/b' in merged[0]['path']


def test_build_rows_handles_bad_usage(logic):
    items = [{'label': 'X', 'path': '/x'}]

    def broken(_path):
        raise OSError('boom')

    assert logic.build_rows(items, broken) == []
    assert logic.build_rows(items, lambda _p: ('bad', 1, 'd')) == []
