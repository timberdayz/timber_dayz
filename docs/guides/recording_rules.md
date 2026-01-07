# 录制规则 v1.0 / Recording Rules v1.0

版本: v1.0 日期: 2025-08-30 适用范围: 新架构 v3.1.x

## 目标 / Goals

- 任何人按“完整流程(complete)”录制，都能产出可直接运行的“端到端下载脚本”。
- 输出脚本与菜单项“1. 🛍️ Shopee 商品表现数据导出 (录制脚本)”一致：登录 → 选择数据类型 → 选择时间范围 → 导出下载。
- 统一命名与索引，支持“稳定版”优先执行。

---

## 一、前置要求 / Prerequisites

- 账号配置必须包含 login_url；录制和回放均以 login_url 为唯一入口。
- 使用增强录制向导 EnhancedRecordingWizard：默认“4. 完整流程录制(complete)”。
- 数据类型 data_type 统一取值：products | orders | analytics | finance。
- 目录规范：
  - 录制脚本: temp/recordings/<platform>/
  - 事件与追踪: temp/media/, temp/logs/
  - 索引文件: data/recordings/registry.json

---

## 二、文件命名 / File Naming

- 统一规范: {平台}_{账号}_{数据类型}_complete_{时间戳}.py
  - 平台 platform 小写英文（示例: shopee）

### 生产级录制（薄封装，调用组件） / Production-grade Recording (Thin Wrapper)

- 目的：产出可回放脚本，但核心逻辑通过组件调用，便于跨账号复用与集中维护。
- 建议结构：
  - from modules.platforms.shopee.adapter import ShopeeAdapter
  - 通过 adapter.login()/navigation()/date_picker()/exporter() 调用组件
  - 脚本仅保留账号/店铺/时间等参数与少量差异化选择器
- 优势：UI 变化时主要修组件或配方，脚本层改动最小；跨账号共享。

#### 生产级录制脚本模板示例

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生产级录制脚本示例：Shopee 商品表现数据导出
文件名：shopee_MyStore_products_complete_20250831_120000.py

特点：
- 薄封装：核心逻辑通过组件调用
- 跨账号复用：仅参数化差异
- 易维护：UI变化时主要修组件
"""

from playwright.sync_api import sync_playwright
from modules.components.base import ExecutionContext
from modules.platforms.shopee.adapter import ShopeeAdapter
from modules.components.navigation.base import TargetPage
from modules.components.date_picker.base import DateOption
from modules.core.logger import get_logger
import logging

logger = get_logger(__name__)

def main():
    """主执行函数"""
    # 账号配置（录制时自动填入）
    account = {
        'username': 'your_username',
        'password': 'your_password',
        'login_url': 'https://seller.shopee.cn/account/signin?next=...',
        'store_name': 'MyStore',
        'shop_id': '1234567890',  # 目标店铺ID
    }

    # 执行参数（录制时用户选择）
    target_page = TargetPage.PRODUCTS_PERFORMANCE
    date_option = DateOption.YESTERDAY  # 或 LAST_7_DAYS, LAST_30_DAYS

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            # 构造执行上下文
            ctx = ExecutionContext(
                platform='shopee',
                account=account,
                logger=logger
            )
            adapter = ShopeeAdapter(ctx)

            # 组件化执行流程
            logger.info("🚀 开始执行生产级录制脚本")

            # 1. 登录
            login_result = adapter.login().run(page)
            if not login_result.success:
                logger.error(f"❌ 登录失败: {login_result.message}")
                return False

            # 2. 导航到目标页面
            nav_result = adapter.navigation().run(page, target_page)
            if not nav_result.success:
                logger.error(f"❌ 导航失败: {nav_result.message}")
                return False

            # 3. 选择时间范围
            date_result = adapter.date_picker().run(page, date_option)
            if not date_result.success:
                logger.error(f"❌ 日期选择失败: {date_result.message}")
                return False

            # 4. 导出数据
            export_result = adapter.exporter().run(page)
            if not export_result.success:
                logger.error(f"❌ 导出失败: {export_result.message}")
                return False

            logger.info("✅ 生产级录制脚本执行成功")
            return True

        except Exception as e:
            logger.error(f"❌ 脚本执行异常: {e}")
            return False
        finally:
            browser.close()

def test_recording():
    """测试入口（兼容录制系统）"""
    return main()

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
```

- 账号 account 采用安全 slug（仅字母数字._-，其余替换为 _）
- 数据类型 data_type ∈ {products, orders, analytics, finance}
- 时间戳格式: YYYYMMDD_HHMMSS

- 示例: shopee_MyStore_SG_products_complete_20250830_120000.py
- 历史兼容: {account}_collection_{dtype}_{ts}.py 与 {account}\_complete_{dtype}\_{ts}.py 仍被索引识别。

---

## 三、稳定版管理 / Stable Version Management

- 菜单“运行录制脚本 → [数据类型子菜单] → m. 管理稳定版脚本（查看/设置/取消）”。
- 选择“设置当前最新为稳定版”后，后续执行优先使用稳定版；若未设置，则回退到 latest。
- 支持所有数据类型：products / orders / analytics / finance。

---

## 四、完整流程结构 / Complete Flow Structure

录制的脚本必须包含以下四个模块；任何一环缺失都会影响可回放性。

1. 登录 Login

- 入口仅使用账号 login_url（禁止硬编码其他 URL）。
- 支持自动登录或手动录制登录动作；验证码弹窗需留出处理/暂停点。
- 登录完成判定：URL 域名/页面关键元素/导航成功日志。

2. 选择数据类型 Navigate to Data Page

- 导航到目标数据页面（如 Shopee 商品表现/流量表现/订单/财务）。
- 处理 iframe：先 page.frame(...) 或使用 frame_locator，确保在正确上下文中操作。
- 处理通知弹窗/新手引导：在关键操作前尝试关闭（可选的通用关闭步骤）。

3. 选择时间范围 Pick Date Range

- 标准快捷项：昨天 / 过去 7 天 / 过去 30 天。
- 策略：优先 text 选择器，其次稳定的 css 选择器；执行后做显式校验（如标签/控件值变化）。
- 对不支持“今日”的数据页，默认昨天；若页面默认已是“昨天”，跳过切换。

4. 导出与下载 Export & Download

- 定位“导出”按钮 → 等待导出任务完成 → 定位“下载”按钮 → 下载/或确认页面数据已显示。
- 等待策略：轮询状态、按钮可用性、Toast/状态提示；最长超时需记录日志。
- 下载后文件命名与落盘目录由系统统一管理；若页面直接展示数据且无下载，记录为成功。

---

## 五、选择器与稳健性 / Selectors & Robustness

- 选择器优先级：text > role/name > css（尽量避免深层级/动态类名）。
- 元素可见性：等待出现并可点击；必要时增加轻量 sleep 但应以等待为主。
- 容错：
  - 多候选器尝试（按优先级）
  - 弹窗/遮罩层关闭再重试
  - iframe 切换失败回退到页面根再尝试
- 日志：每个关键步骤打印“开始/成功/失败”与所用选择器类型。

---

## 六、录制向导操作要点 / Wizard How-To

1. 选择平台和账号（校验 login_url 存在）。
2. 录制类型选择“4. 完整流程(complete)”——默认已选。
3. 选择数据类型（products/…）。
4. 启动 Inspector 后依次录制：
   - 登录（或确认已登录）
   - 导航到数据页面（可用深链接或菜单路径）
   - 选择时间范围（昨天/7 天/30 天）
   - 点击导出并等待可下载；如直接显示数据则记录成功
5. 完成后 Resume，生成脚本。

---

## 七、Shopee 平台要点 / Shopee Notes

- 登录：严格使用 account.login_url；持久化上下文将自动减少验证码频次。
- 商品表现页：/datacenter/product/performance?cnsc_shop_id={shop_id}
- 时间范围：常用“昨天/过去 7 天/过去 30 天”；页面默认“昨天”时无需重复选择。
- 常见弹窗：公告/通知/新手引导，录制中建议添加一次通用关闭动作（选择器可用 text("知道了") 等）。
- 导出按钮：button:has-text("导出数据")；下载按钮：button:has-text("下载")；
- 校验：导出完成提示/按钮可用性变化；无法下载但页面数据显示也视为成功。

---

## 八、代码骨架建议 / Script Skeleton (示例)

> 仅示例结构，录制后请替换为实操步骤与稳定选择器。

```python
from playwright.sync_api import sync_playwright
import logging, time
logger = logging.getLogger(__name__)

def test_recording():
    account = {
        'username': '...', 'password': '...',
        'login_url': 'https://seller.shopee.cn/account/signin?...',
        'store_name': 'MyStore_SG',
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(viewport={"width":1920,"height":1080})
        page = context.new_page()
        # 1) 登录
        page.goto(account['login_url'])
        # TODO: 填写/点击/等待登录完成（或使用已持久化上下文）
        # 2) 导航商品表现
        page.goto('https://seller.shopee.cn/datacenter/product/performance?cnsc_shop_id=...')
        # 3) 选择时间范围（昨天）
        # 优先 text 选择器
        page.click('css=.eds-date .eds-date-input')
        page.click("text=昨天")
        # 4) 导出并下载
        page.click("button:has-text('导出数据')")
        # 轮询等待任务完成（简化示例）
        for i in range(30):
            time.sleep(2)
            # TODO: 检查按钮/Toast/状态
        # 下载按钮或页面数据展示
        # page.click("button:has-text('下载')")
        logger.info('✅ 导出成功')
```

---

## 九、质量检查清单 / QA Checklist

- 登录是否仅从 login_url 进入且成功？
- 目标页面是否可靠进入（含 iframe/弹窗处理）？
- 时间范围是否按预期选择并已校验？
- 导出与下载是否有明确等待与成功判定？
- 关键步骤是否有日志与兜底重试？
- 脚本命名与位置是否符合规范？
- 可回放入口是否存在：main()/run()/test_recording() 任一？

---

## 十、执行与索引 / Execution & Indexing

- 回放执行器将优先使用“稳定版(stable)”，否则使用最新 latest。
- 通过“管理稳定版脚本”菜单可查看/设置/取消稳定版。
- 录制完成后若要设为稳定版：进入对应数据类型子菜单，选择 m → 设置当前最新为稳定版。

---

## 十一、英文摘要 / English Summary

- Always record the complete flow: Login → Navigate → Pick Date Range → Export/Download.
- Naming: {platform}_{account}_{data*type}\_complete*{timestamp}.py, stored under temp/recordings/{platform}/.
- Prefer text selectors, handle iframe/popups, validate state after actions.
- Shopee: use login_url only; product performance page supports Yesterday/Last7/Last30; export → wait → download or consider data visible as success.
- Use the Stable flag to pin a verified script; execution prefers stable over latest.
