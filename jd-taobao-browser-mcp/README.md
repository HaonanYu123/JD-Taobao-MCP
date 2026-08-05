# 京东 + 淘宝浏览器 MCP

一个本地运行、人工参与的 MCP Server。它用 Playwright 打开真实 Chromium 浏览器，允许 AI 在 **京东、淘宝、天猫** 页面中进行低频浏览、点击普通控件，并提取页面文本与商品数据。

## 能做什么

- 打开京东/淘宝登录页，用户自己扫码、输入验证码或完成安全验证。
- 复用独立浏览器资料目录中的登录状态。
- 搜索商品，返回标题、价格、店铺、评论文本、商品链接和图片；默认 `include_details=true`，会逐个打开结果商品页补齐硬约束字段。
- 京东和淘宝使用独立浏览器资料目录，减少登录态、搜索模式和浏览器可执行文件设置互相影响。
- 打开商品详情，提取标题、价格、店铺、规格、图片、产品链接、产品参数、最多 5 条好评、最多 2 条差评、Meta、JSON-LD 和页面文本摘要。
- 商品详情硬约束：输出必须包含 `product_url`、`product_parameters`、`good_reviews`、`bad_reviews`、`product_parameters_status`、`good_reviews_status`、`bad_reviews_status`。页面没有展示、评价不足、要求人工验证或提取失败时，字段仍返回空数组或不足目标条数，并在对应 `status.reason` 说明原因。
- 通用浏览器操作：打开 URL、列出可点击元素、点击、普通输入、滚动、返回、截图。
- 仅允许京东、淘宝、天猫域名。

## 明确不做

- 不绕过验证码、滑块、安全验证或平台风控。
- 不注入“反检测”脚本，不伪造 `navigator`，不调用隐藏接口规避商品页验证。
- 默认禁止购买、加入购物车、结算、支付、确认收货、收藏、关注、删除、地址修改等状态变更动作。
- 不适合高频、大规模采集。平台页面改版后，部分字段选择器需要维护。

## 项目结构

```text
jd-taobao-browser-mcp/
├─ server.py                       MCP 工具入口
├─ jd_taobao_mcp/
│  ├─ browser.py                   Playwright 持久化浏览器与通用点击
│  ├─ service.py                   搜索和详情页高层流程
│  ├─ safety.py                    域名、敏感输入与交易动作防护
│  └─ extractors/                  京东/淘宝页面提取器
├─ config_examples/                Codex 和通用 MCP 客户端配置
├─ scripts/                        Windows 安装与启动脚本
└─ tests/                          纯逻辑单元测试
```

## Windows 安装

要求：Python 3.11+；推荐 Python 3.12。

PowerShell 中执行：

```powershell
cd C:\你的路径\jd-taobao-browser-mcp
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_windows.ps1
```

脚本会创建 `.venv`、安装 MCP SDK 和 Playwright，并下载 Chromium。

手动安装方式：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env
```

测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 接入 Codex

Codex CLI、IDE 扩展和 ChatGPT 桌面端共享 MCP 配置。最简单的方式是在项目目录运行：

```powershell
codex mcp add jd-taobao-browser --env PLAYWRIGHT_HEADLESS=false --env ALLOW_STATE_CHANGING_ACTIONS=false -- C:\你的路径\jd-taobao-browser-mcp\.venv\Scripts\python.exe C:\你的路径\jd-taobao-browser-mcp\server.py
codex mcp list
```

也可以把 `config_examples/codex-config.toml` 的内容复制到：

```text
%USERPROFILE%\.codex\config.toml
```

然后替换其中路径。建议保留：

```toml
default_tools_approval_mode = "prompt"
tool_timeout_sec = 120
```

## 接入 Cursor、Claude Desktop 等 JSON 配置客户端

参考 `config_examples/mcp-client.json`，把 Python 和 `server.py` 改成绝对路径。

## 首次使用流程

1. 调用 `browser_start()`。该工具会启动默认淘宝浏览器；京东浏览器会在打开京东登录页、京东 URL 或京东搜索时按需启动。
2. 调用 `open_login(platform="jd")` 或 `open_login(platform="taobao")`。
3. 在弹出的浏览器中自行扫码或登录；如出现滑块、验证码，手动完成。
4. 调用 `check_login(platform="...")`。
5. 调用 `search_products(...)` 或 `get_product_detail(url)`。

示例提示：

```text
用 jd-taobao-browser MCP 搜索京东的“RTX 5070 笔记本”，最多返回 10 个，价格 7000 到 12000 元，并按价格从低到高排序。不要点击购买或购物车。
```

```text
打开这个淘宝商品链接，提取标题、当前页面价格、店铺、规格参数和主图；页面要求验证时停止并让我手动处理。
```

## 工具清单

| 工具 | 作用 |
|---|---|
| `browser_start` | 启动默认淘宝浏览器 |
| `browser_status` | 查看京东和淘宝浏览器运行状态 |
| `open_login` | 打开京东/淘宝登录页 |
| `check_login` | 估计是否已登录，不返回 Cookie 值 |
| `open_url` | 打开允许域名 URL |
| `search_products` | 搜索商品并结构化提取；默认补 `product_url`、商品参数、好评、差评硬约束字段 |
| `get_product_detail` | 提取商品详情，硬约束包含 `product_url`、产品参数、最多 5 条好评、最多 2 条差评及 status |
| `page_snapshot` | 获取当前页面可见文本、链接和表单 |
| `extract_current_page` | 快照 + 商品字段综合提取 |
| `list_page_elements` | 给当前可交互元素分配 `e1`、`e2` 等 ref |
| `click_page_element` | 点击普通元素；交易和状态变化动作默认阻止 |
| `type_into_element` | 普通输入；敏感字段拒绝 |
| `scroll_page` | 页面滚动 |
| `go_back` | 返回上一页 |
| `take_screenshot` | 保存本地截图 |
| `browser_close` | 关闭浏览器 |

## 关键配置

复制 `.env.example` 为 `.env` 后修改：

- `PLAYWRIGHT_HEADLESS=false`：保持可见浏览器，便于人工登录与验证。
- `BROWSER_CHANNEL=msedge`：可选，使用本机 Edge；留空使用 Playwright Chromium。
- `BROWSER_EXECUTABLE_PATH`：可选，指定通用 Chromium/Chrome/Edge 可执行文件路径。
- `JD_BROWSER_EXECUTABLE_PATH`：可选，仅京东使用的浏览器可执行文件路径。
- `TAOBAO_BROWSER_EXECUTABLE_PATH`：可选，仅淘宝/天猫使用的浏览器可执行文件路径；未设置时会优先尝试本机 Chrome，再回退到通用配置。
- `TAOBAO_SEARCH_MODE=mobile`：淘宝搜索默认走移动端搜索页；也可设为 `pc` 使用桌面搜索页。
- `BROWSER_PROFILE_DIR`：独立登录资料根目录；程序会在下面分别创建 `jd` 和 `taobao` 子目录。
- `PROXY=http://127.0.0.1:7897`：可选代理。
- `MAX_SEARCH_RESULTS=30`：单次最大结果数。
- `ALLOW_STATE_CHANGING_ACTIONS=false`：保持只读防护。

### 为什么必须使用独立资料目录

Playwright 的持久化上下文会在该目录保存 Cookie、本地存储和登录状态。不要把它指向日常 Chrome/Edge 的默认用户目录；浏览器可能拒绝并发使用，而且自动化默认资料目录可能导致页面加载异常。

## 适配说明

京东和淘宝页面经常改版，搜索结果和详情字段不是稳定 API。本项目采用三层降级：

1. 平台专用 DOM 选择器。
2. 商品链接和卡片文本启发式提取。
3. 商品页的 Meta、JSON-LD 与可见文本兜底。

因此它适合“人机协同浏览和少量数据整理”，不应被理解为稳定的官方商品数据 API。

## 安全边界

- 允许导航域名：`*.jd.com`、`*.360buy.com`、`*.taobao.com`、`*.tmall.com`。
- 拒绝 `file://`、`data:`、`javascript:` 和第三方域名。
- MCP 不读取或返回 Cookie 值，只在登录检查时返回 Cookie 名称。
- 密码、验证码、支付密码、银行卡、身份证、OTP 等字段禁止自动输入。
- 出现验证页面时返回 `requires_user_verification=true`，由用户在浏览器中处理。

## 已知限制

- 地区、会员、登录状态和活动会影响价格。
- 淘宝搜索页可能要求登录或人工验证。
- 懒加载、A/B 测试和页面改版会导致个别字段为空。
- `list_page_elements` 生成的 ref 是临时的，点击或刷新后必须重新获取。
- 同一资料目录不能被两个 MCP 进程同时占用。

## License

MIT
