# JD-Taobao-MCP

这是一个基于 Python 与 Playwright 开发的电商网页自动化 MCP Server，用于在人工参与的前提下浏览京东、淘宝、天猫页面，并将商品搜索结果、详情页信息和页面状态以结构化数据返回给支持 MCP 协议的客户端。

当前主要实现位于 [`jd-taobao-browser-mcp`](./jd-taobao-browser-mcp)：支持商品搜索、详情页访问、商品参数提取、最多 5 条好评与最多 2 条差评整理、页面截图、链接返回和受安全规则保护的普通页面操作。项目默认只读，不会购买、加购、结算、支付、关注、收藏或修改账号信息；扫码、密码、验证码和安全验证必须由用户在本机可见浏览器中手动完成。

详细安装、配置和工具说明见 [`jd-taobao-browser-mcp/README.md`](./jd-taobao-browser-mcp/README.md)。
