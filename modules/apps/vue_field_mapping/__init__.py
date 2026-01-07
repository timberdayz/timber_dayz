#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vue.js字段映射审核应用模块

现代化的Vue.js前端 + FastAPI后端架构
解决Streamlit死循环问题
"""

# 应用元数据
APP_ID = "vue_field_mapping"
NAME = "Vue字段映射审核"
VERSION = "1.0.0"
DESCRIPTION = "基于Vue.js的现代化字段映射审核系统，解决Streamlit死循环问题"

# 应用类
from .app import VueFieldMappingApp

__all__ = ["VueFieldMappingApp"]

