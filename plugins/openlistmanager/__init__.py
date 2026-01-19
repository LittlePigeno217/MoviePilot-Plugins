    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        openlist_available = ALIST_AVAILABLE
        
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-3", "style": "border-radius: 8px;"},
                        "content": [
                            {
                                "component": "VCardText",
                                "props": {"class": "pa-3"},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "d-flex align-center mb-3"},
                                        "content": [
                                            {
                                                "component": "VAvatar",
                                                "props": {"color": "primary", "size": "32", "class": "mr-2"},
                                                "content": [
                                                    {
                                                        "component": "VIcon",
                                                        "props": {"icon": "mdi-cog", "size": "20"},
                                                        "text": ""
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-subtitle-1 font-weight-bold"},
                                                        "text": "基本设置"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                        "text": "配置插件的基本运行参数"
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enabled",
                                                            "label": "启动插件",
                                                            "color": "primary",
                                                            "hideDetails": "auto"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enable_custom_suffix",
                                                            "label": "刮削文件",
                                                            "color": "primary",
                                                            "hint": "额外复制字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)文件",
                                                            "persistentHint": True
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "onlyonce",
                                                            "label": "立即运行复制任务",
                                                            "color": "success",
                                                            "hideDetails": "auto"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "clear_cache",
                                                            "label": "清理统计",
                                                            "color": "warning",
                                                            "hideDetails": "auto"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VDivider",
                                        "props": {"class": "my-3"}
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 4},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enable_wechat_notify",
                                                            "label": "发送通知",
                                                            "color": "primary",
                                                            "hint": "当有复制任务时发送企业微信卡片通知",
                                                            "persistentHint": True
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 4},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "use_moviepilot_config",
                                                            "label": "使用MoviePilot的内置OpenList",
                                                            "color": "primary",
                                                            "hint": "使用MoviePilot中已配置的OpenList实例",
                                                            "persistentHint": True,
                                                            "disabled": not openlist_available
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 4},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "cron",
                                                            "label": "执行周期",
                                                            "placeholder": "0 2 * * *",
                                                            "hint": "Cron表达式，默认每天凌晨2点执行复制任务",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-clock-outline"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VDivider",
                                        "props": {"class": "my-3"}
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "openlist_url",
                                                            "label": "OpenList地址",
                                                            "placeholder": "http://localhost:5244",
                                                            "hint": "请输入完整的OpenList服务地址，如果使用MoviePilot配置则此项可留空",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-link",
                                                            "disabled": self._usemoviepilotconfig and openlist_available
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "openlist_token",
                                                            "label": "OpenList令牌",
                                                            "type": "password",
                                                            "placeholder": "在OpenList后台获取",
                                                            "hint": "在OpenList管理后台的'设置'-'全局'中获取令牌，如果使用MoviePilot配置则此项可留空",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-key",
                                                            "disabled": self._usemoviepilotconfig and openlist_available
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-3", "style": "border-radius: 8px;"},
                        "content": [
                            {
                                "component": "VCardText",
                                "props": {"class": "pa-3"},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "d-flex align-center mb-3"},
                                        "content": [
                                            {
                                                "component": "VAvatar",
                                                "props": {"color": "primary", "size": "32", "class": "mr-2"},
                                                "content": [
                                                    {
                                                        "component": "VIcon",
                                                        "props": {"icon": "mdi-folder-multiple", "size": "20"},
                                                        "text": ""
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-subtitle-1 font-weight-bold"},
                                                        "text": "目录配对设置"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                        "text": "配置源目录和目标目录的映射关系"
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12},
                                                "content": [
                                                    {
                                                        "component": "VTextarea",
                                                        "props": {
                                                            "model": "directory_pairs",
                                                            "label": "目录配对",
                                                            "placeholder": "源目录1#目标目录1\n源目录2#目标目录2",
                                                            "rows": 3,
                                                            "hint": "每行一组配对，使用#分隔源目录和目标目录",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-folder-network"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mb-3", "style": "border-radius: 8px;"},
                        "content": [
                            {
                                "component": "VCardText",
                                "props": {"class": "pa-3"},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "d-flex align-center mb-3"},
                                        "content": [
                                            {
                                                "component": "VAvatar",
                                                "props": {"color": "primary", "size": "32", "class": "mr-2"},
                                                "content": [
                                                    {
                                                        "component": "VIcon",
                                                        "props": {"icon": "mdi-file-video", "size": "20"},
                                                        "text": ""
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-subtitle-1 font-weight-bold"},
                                                        "text": "Strm生成设置"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                        "text": "配置Strm文件生成相关参数"
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enable_strm",
                                                            "label": "启用Strm生成",
                                                            "color": "primary",
                                                            "hideDetails": "auto"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSelect",
                                                        "props": {
                                                            "model": "strm_mode",
                                                            "label": "生成模式",
                                                            "items": [
                                                                {"text": "全量生成", "value": "full"},
                                                                {"text": "增量生成", "value": "incremental"}
                                                            ],
                                                            "hideDetails": "auto",
                                                            "persistentHint": True,
                                                            "hint": "全量生成：重新生成所有Strm文件；增量生成：只生成新增或修改的文件"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "strm_onlyonce",
                                                            "label": "立即生成Strm文件",
                                                            "color": "success",
                                                            "hideDetails": "auto"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VDivider",
                                        "props": {"class": "my-3"}
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "strm_target_dir",
                                                            "label": "Strm文件保存目录",
                                                            "placeholder": "/strm",
                                                            "hint": "请输入Strm文件保存的目录路径",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-folder-video"
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "sm": 6},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "strm_prefix",
                                                            "label": "Strm文件内容前缀",
                                                            "placeholder": "http://localhost:5244",
                                                            "hint": "Strm文件内容的前缀，用于生成完整的播放链接",
                                                            "persistentHint": True,
                                                            "prependIcon": "mdi-link"
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "mt-3", "style": "border-radius: 8px;"},
                        "content": [
                            {
                                "component": "VCardText",
                                "props": {"class": "pa-3"},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "d-flex align-center mb-3"},
                                        "content": [
                                            {
                                                "component": "VAvatar",
                                                "props": {"color": "info", "size": "32", "class": "mr-2"},
                                                "content": [
                                                    {
                                                        "component": "VIcon",
                                                        "props": {"icon": "mdi-information", "size": "20"},
                                                        "text": ""
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-subtitle-1 font-weight-bold"},
                                                        "text": "说明信息"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-grey-darken-1"},
                                                        "text": "插件使用说明和注意事项"
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 6},
                                                "content": [
                                                    {
                                                        "component": "VAlert",
                                                        "props": {
                                                            "type": "info",
                                                            "text": True,
                                                            "variant": "tonal",
                                                            "class": "mb-0",
                                                            "density": "compact"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "font-weight-bold mb-1"},
                                                                "text": "文件尾缀说明："
                                                            },
                                                            {
                                                                "component": "div", 
                                                                "text": "• 默认：自动匹配常用视频格式（mp4, mkv, avi, mov等）"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 勾选复制字幕/元数据/封面图：额外匹配字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 6},
                                                "content": [
                                                    {
                                                        "component": "VAlert",
                                                        "props": {
                                                            "type": "warning",
                                                            "text": True,
                                                            "variant": "tonal",
                                                            "class": "mb-0",
                                                            "density": "compact"
                                                        },
                                                        "content": [
                                                            {
                                                                "component": "div",
                                                                "props": {"class": "font-weight-bold mb-1"},
                                                                "text": "清除缓存说明："
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 勾选此选项后保存，将清空所有复制记录和任务状态"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 插件将重新开始记录复制历史"
                                                            },
                                                            {
                                                                "component": "div",
                                                                "text": "• 此操作不可逆，请谨慎使用"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enable,
            "onlyonce": self._onlyonce,
            "clear_cache": self._clearcache,
            "openlist_url": self._openlist_url,
            "openlist_token": self._openlist_token,
            "directory_pairs": self._directory_pairs,
            "enable_custom_suffix": self._enablecustomsuffix,
            "use_moviepilot_config": self._usemoviepilotconfig,
            "enable_wechat_notify": self._notify,
            "cron": self._cron or "0 2 * * *",
            "enable_strm": self._enable_strm,
            "strm_mode": self._strm_mode,
            "strm_target_dir": self._strm_target_dir,
            "strm_prefix": self._strm_prefix,
            "strm_onlyonce": self._strm_onlyonce
        }