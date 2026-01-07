#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统配置API - v4.3.5
提供系统级配置和常量
"""

from fastapi import APIRouter
from backend.utils.api_response import success_response
from modules.core.validators import VALID_PLATFORMS, VALID_DATA_DOMAINS, VALID_GRANULARITIES

router = APIRouter(prefix="/system", tags=["系统配置"])


@router.get("/platforms")
async def get_platforms():
    """
    获取支持的平台列表（白名单）
    
    Returns:
        list: 平台列表
    """
    return success_response(data={"platforms": sorted(list(VALID_PLATFORMS))})


@router.get("/data-domains")
async def get_data_domains():
    """
    获取支持的数据域列表（白名单）
    
    Returns:
        list: 数据域列表
    """
    return success_response(data={"data_domains": sorted(list(VALID_DATA_DOMAINS))})


@router.get("/granularities")
async def get_granularities():
    """
    获取支持的粒度列表（白名单）
    
    Returns:
        list: 粒度列表
    """
    return success_response(data={"granularities": sorted(list(VALID_GRANULARITIES))})


@router.get("/constants")
async def get_all_constants():
    """
    获取所有系统常量（一次性获取）
    
    Returns:
        dict: 所有常量
    """
    data = {
        "platforms": sorted(list(VALID_PLATFORMS)),
        "data_domains": sorted(list(VALID_DATA_DOMAINS)),
        "granularities": sorted(list(VALID_GRANULARITIES))
    }
    
    return success_response(data=data)

