#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
网页元素类型定义

定义各种网页元素的类型和操作方式
"""

from enum import Enum
from typing import Dict, List, Any, Optional

class ElementType(Enum):
    """元素类型枚举"""
    
    # 登录相关
    USERNAME_INPUT = "username_input"           # 用户名输入框
    PASSWORD_INPUT = "password_input"           # 密码输入框
    EMAIL_INPUT = "email_input"                 # 邮箱输入框
    PHONE_INPUT = "phone_input"                 # 手机输入框
    CAPTCHA_INPUT = "captcha_input"             # 验证码输入框
    LOGIN_BUTTON = "login_button"               # 登录按钮
    
    # 表单元素
    TEXT_INPUT = "text_input"                   # 文本输入框
    NUMBER_INPUT = "number_input"               # 数字输入框
    DATE_PICKER = "date_picker"                 # 日期选择器
    TIME_PICKER = "time_picker"                 # 时间选择器
    DROPDOWN = "dropdown"                       # 下拉框
    CHECKBOX = "checkbox"                       # 复选框
    RADIO_BUTTON = "radio_button"               # 单选框
    TEXTAREA = "textarea"                       # 文本域
    
    # 操作按钮
    SUBMIT_BUTTON = "submit_button"             # 提交按钮
    CANCEL_BUTTON = "cancel_button"             # 取消按钮
    DOWNLOAD_BUTTON = "download_button"         # 下载按钮
    UPLOAD_BUTTON = "upload_button"             # 上传按钮
    SEARCH_BUTTON = "search_button"             # 搜索按钮
    DELETE_BUTTON = "delete_button"             # 删除按钮
    EDIT_BUTTON = "edit_button"                 # 编辑按钮
    SAVE_BUTTON = "save_button"                 # 保存按钮
    
    # 数据展示
    TABLE = "table"                             # 表格
    LIST = "list"                               # 列表
    CARD = "card"                               # 卡片
    PRODUCT_NAME = "product_name"               # 产品名称
    PRODUCT_PRICE = "product_price"             # 产品价格
    PRODUCT_IMAGE = "product_image"             # 产品图片
    ORDER_NUMBER = "order_number"               # 订单号
    
    # 导航元素
    MENU_ITEM = "menu_item"                     # 菜单项
    TAB = "tab"                                 # 标签页
    BREADCRUMB = "breadcrumb"                   # 面包屑
    PAGINATION = "pagination"                   # 分页
    
    # 通用元素
    LINK = "link"                               # 链接
    IMAGE = "image"                             # 图片
    TEXT = "text"                               # 文本
    CONTAINER = "container"                     # 容器


class ElementAction(Enum):
    """元素操作类型"""
    
    CLICK = "click"                             # 点击
    FILL = "fill"                               # 填充文本
    SELECT = "select"                           # 选择选项
    CHECK = "check"                             # 勾选
    UNCHECK = "uncheck"                         # 取消勾选
    UPLOAD = "upload"                           # 上传文件
    DOWNLOAD = "download"                       # 下载文件
    HOVER = "hover"                             # 悬停
    DRAG = "drag"                               # 拖拽
    GET_TEXT = "get_text"                       # 获取文本
    GET_ATTRIBUTE = "get_attribute"             # 获取属性
    SCREENSHOT = "screenshot"                   # 截图
    WAIT = "wait"                               # 等待


class ElementSelectorGroup:
    """元素选择器组"""
    
    def __init__(self, element_type: ElementType):
        self.element_type = element_type
        self.selectors: List[str] = []
        self.keywords: List[str] = []
        self.attributes: Dict[str, Any] = {}
        self.validation_rules: List[str] = []
    
    def add_selector(self, selector: str, priority: int = 1):
        """添加CSS选择器"""
        self.selectors.append(selector)
        return self
    
    def add_keyword(self, keyword: str):
        """添加关键词匹配"""
        self.keywords.append(keyword)
        return self
    
    def add_attribute(self, name: str, value: Any):
        """添加属性要求"""
        self.attributes[name] = value
        return self
    
    def add_validation(self, rule: str):
        """添加验证规则"""
        self.validation_rules.append(rule)
        return self


# 预定义的元素选择器配置
ELEMENT_SELECTORS = {
    ElementType.USERNAME_INPUT: ElementSelectorGroup(ElementType.USERNAME_INPUT)
        .add_selector('input[name="username"]')
        .add_selector('input[name="email"]')
        .add_selector('input[name="account"]')
        .add_selector('input[name="loginName"]')
        .add_selector('input[type="text"]')
        .add_selector('input[type="email"]')
        .add_selector('input.username')
        .add_selector('input.login-username')
        .add_selector('#username')
        .add_selector('#email')
        .add_keyword('用户名')
        .add_keyword('邮箱')
        .add_keyword('账号')
        .add_keyword('手机号')
        .add_keyword('username')
        .add_keyword('email')
        .add_validation('is_visible')
        .add_validation('is_enabled'),
        
    ElementType.PASSWORD_INPUT: ElementSelectorGroup(ElementType.PASSWORD_INPUT)
        .add_selector('input[type="password"]')
        .add_selector('input[name="password"]')
        .add_selector('input[name="pwd"]')
        .add_selector('input.password')
        .add_selector('input.login-password')
        .add_selector('#password')
        .add_selector('#pwd')
        .add_keyword('密码')
        .add_keyword('口令')
        .add_keyword('password')
        .add_validation('is_visible')
        .add_validation('is_enabled'),
        
    ElementType.LOGIN_BUTTON: ElementSelectorGroup(ElementType.LOGIN_BUTTON)
        .add_selector('button[type="submit"]')
        .add_selector('input[type="submit"]')
        .add_selector('button:has-text("登录")')
        .add_selector('button:has-text("登 录")')
        .add_selector('button:has-text("登  录")')
        .add_selector('a:has-text("登录")')
        .add_selector('a:has-text("登 录")')
        .add_selector('a:has-text("登  录")')
        .add_selector('button.login-btn')
        .add_selector('button.btn-login')
        .add_selector('.login-button')
        .add_selector('#loginBtn')
        .add_keyword('登录')
        .add_keyword('登 录')
        .add_keyword('登  录')
        .add_keyword('login')
        .add_keyword('sign in')
        .add_validation('is_visible')
        .add_validation('is_enabled'),
        
    ElementType.CAPTCHA_INPUT: ElementSelectorGroup(ElementType.CAPTCHA_INPUT)
        .add_selector('input[name="captcha"]')
        .add_selector('input[name="code"]')
        .add_selector('input[name="verifyCode"]')
        .add_selector('input[name="checkcode"]')
        .add_selector('input.captcha')
        .add_selector('input.verify-code')
        .add_selector('#captcha')
        .add_selector('#verifyCode')
        .add_keyword('验证码')
        .add_keyword('图形验证码')
        .add_keyword('captcha')
        .add_keyword('verify code')
        .add_validation('is_visible')
        .add_validation('is_enabled'),
        
    ElementType.DOWNLOAD_BUTTON: ElementSelectorGroup(ElementType.DOWNLOAD_BUTTON)
        .add_selector('a[href*="download"]')
        .add_selector('button:has-text("下载")')
        .add_selector('button:has-text("导出")')
        .add_selector('a:has-text("下载")')
        .add_selector('a:has-text("导出")')
        .add_selector('.download-btn')
        .add_selector('.export-btn')
        .add_selector('button[onclick*="download"]')
        .add_keyword('下载')
        .add_keyword('导出')
        .add_keyword('download')
        .add_keyword('export')
        .add_validation('is_visible')
        .add_validation('is_enabled'),
        
    ElementType.DATE_PICKER: ElementSelectorGroup(ElementType.DATE_PICKER)
        .add_selector('input[type="date"]')
        .add_selector('input.date-picker')
        .add_selector('input.datepicker')
        .add_selector('.ant-picker')
        .add_selector('.el-date-picker')
        .add_selector('.date-input')
        .add_keyword('日期')
        .add_keyword('时间')
        .add_keyword('date')
        .add_validation('is_visible')
        .add_validation('is_enabled'),
        
    ElementType.PRODUCT_PRICE: ElementSelectorGroup(ElementType.PRODUCT_PRICE)
        .add_selector('.price')
        .add_selector('.product-price')
        .add_selector('.money')
        .add_selector('.amount')
        .add_selector('[class*="price"]')
        .add_selector('[class*="money"]')
        .add_keyword('价格')
        .add_keyword('金额')
        .add_keyword('¥')
        .add_keyword('$')
        .add_keyword('€')
        .add_keyword('price')
        .add_keyword('amount'),
        
    ElementType.PRODUCT_NAME: ElementSelectorGroup(ElementType.PRODUCT_NAME)
        .add_selector('.product-name')
        .add_selector('.product-title')
        .add_selector('.item-name')
        .add_selector('.goods-name')
        .add_selector('[class*="product"][class*="name"]')
        .add_selector('[class*="item"][class*="title"]')
        .add_keyword('产品名称')
        .add_keyword('商品名称')
        .add_keyword('标题')
        .add_keyword('title')
        .add_keyword('name'),
}
