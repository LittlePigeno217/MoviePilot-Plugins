import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from plugins.u115mediaupload.api_handlers import U115MediaUploadApiHandler
from plugins.u115mediaupload.records import PathMappingManager


def test_generate_qrcode():
    """测试二维码生成"""
    client = Mock()
    client.generate_qrcode.return_value = {
        "success": True,
        "data": {"codeContent": "https://115.com/qrcode/test"}
    }

    manager = Mock(spec=PathMappingManager)
    handler = U115MediaUploadApiHandler(client, manager)

    result = handler.generate_qrcode()

    assert result["success"] is True
    assert "qrcode" in result["data"]
    assert result["data"]["qrcode"].startswith("data:image/png;base64,")
    assert result["data"]["codeContent"] == "https://115.com/qrcode/test"


def test_browse_local_root(tmp_path):
    """测试浏览本地目录根目录"""
    # 创建测试目录结构
    (tmp_path / "movie1").mkdir()
    (tmp_path / "movie2").mkdir()
    (tmp_path / ".hidden").mkdir()

    client = Mock()
    manager = Mock(spec=PathMappingManager)
    handler = U115MediaUploadApiHandler(client, manager)

    # 模拟 settings.LIBRARY_PATH
    with patch("plugins.u115mediaupload.api_handlers.settings") as mock_settings:
        mock_settings.LIBRARY_PATH = str(tmp_path)

        result = handler.browse_local("")

        assert result["success"] is True
        assert result["data"]["base"] == str(tmp_path)
        assert result["data"]["current"] == ""
        assert len(result["data"]["items"]) == 2
        assert result["data"]["items"][0]["name"] == "movie1"
        assert result["data"]["items"][0]["is_dir"] is True


def test_browse_local_subdirectory(tmp_path):
    """测试浏览本地子目录"""
    # 创建测试目录结构
    movies_dir = tmp_path / "movies"
    movies_dir.mkdir()
    (movies_dir / "movie1").mkdir()
    (movies_dir / "movie2").mkdir()

    client = Mock()
    manager = Mock(spec=PathMappingManager)
    handler = U115MediaUploadApiHandler(client, manager)

    with patch("plugins.u115mediaupload.api_handlers.settings") as mock_settings:
        mock_settings.LIBRARY_PATH = str(tmp_path)

        result = handler.browse_local("movies")

        assert result["success"] is True
        assert result["data"]["current"] == "movies"
        assert len(result["data"]["items"]) == 2


def test_browse_115_with_cache(tmp_path):
    """测试 115 目录浏览和缓存"""
    client = Mock()
    client.get_dir_list.return_value = [
        {"name": "folder1", "cid": "123", "type": 1},
        {"name": "folder2", "cid": "124", "type": 1},
    ]

    manager = PathMappingManager(config_path=str(tmp_path))
    handler = U115MediaUploadApiHandler(client, manager)

    # 第一次调用（无缓存）
    result1 = handler.browse_115("0", refresh=False)
    assert result1["success"] is True
    assert result1["data"]["cached"] is False
    assert len(result1["data"]["items"]) == 2

    # 第二次调用（有缓存）
    result2 = handler.browse_115("0", refresh=False)
    assert result2["success"] is True
    assert result2["data"]["cached"] is True

    # 调用刷新
    client.get_dir_list.return_value = [
        {"name": "folder1", "cid": "123", "type": 1},
    ]
    result3 = handler.browse_115("0", refresh=True)
    assert result3["success"] is True
    assert result3["data"]["cached"] is False
    assert len(result3["data"]["items"]) == 1


def test_save_path_mappings(tmp_path):
    """测试保存路径映射"""
    client = Mock()
    manager = PathMappingManager(config_path=str(tmp_path))
    handler = U115MediaUploadApiHandler(client, manager)

    mappings = [
        {
            "enabled": True,
            "source": "/movies",
            "sourceDesc": "movies",
            "target": "/115/movies",
            "targetCid": "123"
        },
        {
            "enabled": False,
            "source": "/tv",
            "sourceDesc": "tv",
            "target": "/115/tv",
            "targetCid": "124"
        }
    ]

    result = handler.save_path_mappings(mappings)

    assert result["success"] is True

    # 验证保存结果
    saved = manager.get_mappings()
    assert len(saved) == 2
    assert saved[0].source == "/movies"
    assert saved[1].enabled is False


def test_browse_115_no_client():
    """测试 115 目录浏览无客户端情况"""
    manager = Mock(spec=PathMappingManager)
    handler = U115MediaUploadApiHandler(None, manager)

    result = handler.browse_115("0")

    assert result["success"] is False
    assert "未初始化" in result["msg"]


def test_browse_local_invalid_path(tmp_path):
    """测试浏览本地无效路径"""
    client = Mock()
    manager = Mock(spec=PathMappingManager)
    handler = U115MediaUploadApiHandler(client, manager)

    with patch("plugins.u115mediaupload.api_handlers.settings") as mock_settings:
        mock_settings.LIBRARY_PATH = str(tmp_path)

        result = handler.browse_local("nonexistent")

        assert result["success"] is False
        assert "不存在" in result["msg"]


def test_browse_115_filters_directories():
    """测试 115 目录浏览过滤非目录项"""
    client = Mock()
    client.get_dir_list.return_value = [
        {"name": "folder1", "cid": "123", "type": 1},  # 目录
        {"name": "file1.txt", "cid": "124", "type": 0},  # 文件
        {"name": "folder2", "cid": "125", "type": 1},  # 目录
    ]

    manager = Mock(spec=PathMappingManager)
    manager.get_115_cache.return_value = None
    manager.set_115_cache.return_value = True
    handler = U115MediaUploadApiHandler(client, manager)

    result = handler.browse_115("0")

    assert result["success"] is True
    # 应该只返回 2 个目录，文件被过滤掉
    assert len(result["data"]["items"]) == 2
    assert all(item["is_dir"] for item in result["data"]["items"])
