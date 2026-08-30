# 易破解签到站点分析

- 站点: https://www.ypojie.com/vip
- 已登录会员中心页面存在按钮: `.erphp-checkin`
- 前端 JS: `/wp-content/plugins/erphpdown/static/erphpdown.js`
- 签到通过 WordPress AJAX 完成:
  - POST `/wp-admin/admin-ajax.php`
  - 表单: `action=epd_checkin`
- 已实测响应:
  - HTTP 200
  - `{"status":200,"msg":null}`
- 初步判断:
  - 依赖登录 Cookie
  - 成功态为 JSON `status == 200`
  - 失败态应读取 `msg`
- 后端适配建议:
  - 新增 `ypojie` 站点适配器
  - 配置方式使用 Cookie
  - 请求头带 `Cookie`, `User-Agent`, `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`, `Origin`, `Referer`
  - 结果消息兼容 `msg == null` 时显示“签到成功”
