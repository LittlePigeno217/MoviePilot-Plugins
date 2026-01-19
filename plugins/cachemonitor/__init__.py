from abc import ABCMeta, abstractmethod
from typing import List, Dict, Tuple, Optional, Any
import time

from app.plugins import _PluginBase
from app.core.cache import cache


class cachemonitor(_PluginBase):
    """
    缓存监控插件
    """
    # 插件名称
    plugin_name = "缓存监控"
    # 插件描述
    plugin_desc = "实时监控和管理系统缓存数据"
    # 插件顺序
    plugin_order = 100

    def __init__(self):
        super().__init__()
        # 插件状态
        self._enabled = False
        # 缓存数据
        self._cache_data = {}
        # 上次更新时间
        self._last_update = 0

    def init_plugin(self, config: dict = None):
        """
        生效配置信息
        """
        if config:
            self._enabled = config.get("enabled", False)
        else:
            self._enabled = True
        self.refresh_cache_data()

    def get_state(self) -> bool:
        """
        获取插件运行状态
        """
        return self._enabled

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        """
        获取插件渲染模式
        """
        return "vue", "dist"

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件API
        """
        return [
            {
                "path": "/cache",
                "endpoint": self.get_cache_data,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "获取缓存数据",
                "description": "获取系统缓存数据"
            },
            {
                "path": "/cache/refresh",
                "endpoint": self.refresh_cache_data,
                "methods": ["POST"],
                "auth": "apikey",
                "summary": "刷新缓存数据",
                "description": "刷新系统缓存数据"
            },
            {
                "path": "/cache/clear",
                "endpoint": self.clear_cache,
                "methods": ["POST"],
                "auth": "apikey",
                "summary": "清除缓存",
                "description": "清除指定缓存或全部缓存"
            }
        ]

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """
        拼装插件配置页面
        """
        return None, {"enabled": True}

    def get_page(self) -> Optional[List[dict]]:
        """
        拼装插件详情页面
        """
        return None

    def stop_service(self):
        """
        停止插件服务
        """
        self._enabled = False

    def get_cache_data(self):
        """
        获取缓存数据
        """
        # 如果超过5秒未更新，则刷新数据
        if time.time() - self._last_update > 5:
            self.refresh_cache_data()
        return {
            "code": 0,
            "message": "success",
            "data": {
                "cache_list": self._cache_data,
                "total_count": len(self._cache_data),
                "last_update": self._last_update
            }
        }

    def refresh_cache_data(self):
        """
        刷新缓存数据
        """
        cache_data = {}
        try:
            # 获取缓存中的所有键
            keys = cache.keys()
            for key in keys:
                try:
                    # 获取缓存值和过期时间
                    value = cache.get(key)
                    ttl = cache.ttl(key)
                    cache_data[key] = {
                        "value": str(value)[:100] + "..." if len(str(value)) > 100 else str(value),
                        "ttl": ttl,
                        "size": len(str(value))
                    }
                except Exception as e:
                    cache_data[key] = {
                        "value": f"获取失败: {str(e)}",
                        "ttl": -1,
                        "size": 0
                    }
        except Exception as e:
            return {
                "code": 1,
                "message": f"获取缓存数据失败: {str(e)}",
                "data": {}
            }
        
        self._cache_data = cache_data
        self._last_update = time.time()
        
        return {
            "code": 0,
            "message": "success",
            "data": {
                "total_count": len(cache_data),
                "last_update": self._last_update
            }
        }

    def clear_cache(self, key: str = None):
        """
        清除缓存
        """
        try:
            if key:
                cache.delete(key)
                message = f"缓存 {key} 已清除"
            else:
                cache.clear()
                message = "所有缓存已清除"
            
            # 刷新缓存数据
            self.refresh_cache_data()
            
            return {
                "code": 0,
                "message": message,
                "data": {}
            }
        except Exception as e:
            return {
                "code": 1,
                "message": f"清除缓存失败: {str(e)}",
                "data": {}
            }
