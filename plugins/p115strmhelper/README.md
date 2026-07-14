# 115 STRM 助手（P115StrmHelper）

扫描 115 网盘目录生成 `.strm`，经插件的 302 重定向端点流式播放（不下载媒体本体）。

## 功能
- 扫码（二维码图片）/ Cookie 授权
- 115 与本地目录浏览选择
- STRM 生成、302 重定向播放（链接每次播放实时换取，永不过期）
- 定时同步、增量同步、刮削文件同步（nfo/海报/字幕）、多目录映射

## 播放原理
`.strm` 内容为指向插件重定向端点的 URL：

```
http://{MoviePilot地址}/api/v1/plugin/P115StrmHelper/redirect?pickcode={pickcode}&apikey={API_TOKEN}
```

Emby/Jellyfin 播放时请求该 URL，插件用 115 换取新的下载直链并 302 跳转。

## 配置要点
- **MoviePilot 地址**：必须填媒体服务器能访问到的地址（如 `http://10.10.10.3:3001`），否则 `.strm` 不可播。
- **115 APP ID**：扫码登录所需；留空则回退 MoviePilot 全局 `U115_APP_ID`。
- 更新（非重装）后若提示缺少 `qrcode`，在实例执行一次 `pip install qrcode`。

## 致谢与许可
灵感来源 [DDSRem-Dev/MoviePilot-Plugins](https://github.com/DDSRem-Dev/MoviePilot-Plugins) 的 p115strmhelper。本插件为原创实现，遵循 GPL-3.0。
