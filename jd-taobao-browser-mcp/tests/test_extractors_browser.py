import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_browser_path = PROJECT_ROOT / ".ms-playwright"
if project_browser_path.exists():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(project_browser_path))

import pytest
from playwright.async_api import async_playwright

from jd_taobao_mcp.extractors.detail import extract_product_detail
from jd_taobao_mcp.extractors.search import extract_jd_search, extract_taobao_search


@pytest.mark.asyncio
async def test_jd_search_extractor():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(
            '''
            <ul id="J_goodsList">
              <li class="gl-item">
                <div class="p-name"><a href="https://item.jd.com/123.html"><em>测试笔记本</em></a></div>
                <div class="p-price"><i>6999.00</i></div>
                <div class="p-shop"><a>测试京东店</a></div>
                <div class="p-commit"><a>1万+评价</a></div>
                <img src="https://img.example/1.jpg" />
              </li>
            </ul>
            '''
        )
        items = await extract_jd_search(page, 10)
        assert items[0]["title"] == "测试笔记本"
        assert items[0]["price"] == 6999.0
        assert items[0]["shop"] == "测试京东店"
        assert items[0]["product_url"] == "https://item.jd.com/123.html"
        await browser.close()


@pytest.mark.asyncio
async def test_jd_search_extractor_react_chat_link_fallback():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(
            '''
            <a href="https://chat.jd.com/index.action?entry=jd_search&pid=123456&wname=%E6%B5%8B%E8%AF%95AI%E6%9C%BA%E5%99%A8%E4%BA%BA&seller=%E6%B5%8B%E8%AF%95%E5%BA%97&commentNum=100%2B">客服</a>
            '''
        )
        items = await extract_jd_search(page, 10)
        assert items[0]["title"] == "测试AI机器人"
        assert items[0]["url"] == "https://item.jd.com/123456.html"
        assert items[0]["product_url"] == "https://item.jd.com/123456.html"
        assert items[0]["shop"] == "测试店"
        await browser.close()


@pytest.mark.asyncio
async def test_taobao_search_extractor():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(
            '''
            <div class="item-card" data-spm="x">
              <a href="https://item.taobao.com/item.htm?id=9" title="测试耳机">测试耳机</a>
              <span>¥299.00</span>
            </div>
            '''
        )
        items = await extract_taobao_search(page, 10)
        assert items[0]["title"] == "测试耳机"
        assert items[0]["price"] == 299.0
        await browser.close()


@pytest.mark.asyncio
async def test_detail_extractor():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(
            '''
            <meta property="og:title" content="测试商品" />
            <meta property="og:image" content="https://img.example/main.jpg" />
            <div class="sku-name">测试商品</div>
            <div class="p-price"><span class="price">1299.00</span></div>
            <div class="shop-name">测试店铺</div>
            <ul class="p-parameter-list"><li>颜色：黑色</li></ul>
            <div class="Ptable-item">
              <h3>Base</h3>
              <dl><dt>Capacity</dt><dd>3L</dd></dl>
            </div>
            <div class="comment-item">
              <div class="user-info">u-positive</div>
              <div class="comment-con">\u5f88\u597d\u7528\uff0c\u64cd\u4f5c\u7b80\u5355\uff0c\u503c\u5f97\u63a8\u8350</div>
              <div class="comment-op">12\u4eba\u70b9\u8d5e</div>
            </div>
            <div class="comment-item">
              <div class="user-info">u-negative</div>
              <div class="comment-con">\u4e0d\u597d\u7528\uff0c\u7c98\u9505\uff0c\u6709\u5f02\u5473\uff0c\u4e0d\u63a8\u8350</div>
              <div class="comment-op">8\u4eba\u70b9\u8d5e</div>
            </div>
            <script type="application/ld+json">
              {"@type":"Product","name":"测试商品","offers":{"price":"1299.00"}}
            </script>
            '''
        )
        data = await extract_product_detail(page, "jd")
        assert data["title"] == "测试商品"
        assert data["product_url"].startswith("about:")
        assert data["price"] == 1299.0
        assert {"name": "Capacity", "value": "3L", "group": "Base"} in data["product_parameters"]
        assert data["high_praise_reviews"][0]["user"] == "u-positive"
        assert data["high_praise_reviews"][0]["helpful_count"] == 12
        assert data["high_dissatisfied_reviews"][0]["user"] == "u-negative"
        assert data["high_dissatisfied_reviews"][0]["helpful_count"] == 8
        assert data["shop"] == "测试店铺"
        assert "颜色：黑色" in data["specifications"]
        await browser.close()
