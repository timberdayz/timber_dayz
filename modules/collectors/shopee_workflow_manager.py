#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee数据采集工作流管理器
整合登录验证码、页面分析、数据下载和账号级别数据归总功能
支持多账号并行采集和智能错误处理
"""

import time
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict

from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext

from modules.utils.sessions.session_manager import SessionManager
from modules.utils.otp.verification_service import VerificationCodeService
from modules.utils.page_analysis_tool import PageAnalysisTool
from modules.collectors.shopee_page_analyzer import ShopeePageAnalyzer
from modules.collectors.shopee_collector import ShopeeCollector

logger = logging.getLogger(__name__)

@dataclass
class WorkflowStep:
    """工作流步骤"""
    name: str
    status: str  # pending, running, completed, failed
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

@dataclass
class AccountWorkflowResult:
    """账号工作流结果"""
    account_id: str
    store_name: str
    workflow_id: str
    start_time: str
    end_time: str
    duration: float
    steps: List[WorkflowStep]
    success: bool
    data_files: List[str]
    analysis_files: List[str]
    error_summary: Optional[str] = None

@dataclass
class MultiAccountWorkflowResult:
    """多账号工作流结果"""
    workflow_id: str
    start_time: str
    end_time: str
    total_accounts: int
    successful_accounts: int
    failed_accounts: int
    account_results: List[AccountWorkflowResult]
    summary: Dict[str, Any]

class ShopeeWorkflowManager:
    """Shopee数据采集工作流管理器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化工作流管理器
        
        Args:
            config: 工作流配置
        """
        self.config = config or {}
        self.workflow_id = f"shopee_workflow_{int(time.time())}"
        self.start_time = datetime.now().isoformat()
        self.verification_service = VerificationCodeService()
        self.session_manager = SessionManager()
        
        # 工作流步骤定义
        self.workflow_steps = [
            "account_validation",
            "browser_initialization", 
            "session_restoration",
            "login_verification",
            "page_analysis",
            "data_collection",
            "data_download",
            "data_consolidation",
            "cleanup"
        ]
        
        # 输出目录
        self.output_base = Path("temp/outputs/shopee_workflow")
        self.output_base.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[START] 初始化Shopee工作流管理器: {self.workflow_id}")
        logger.info(f"   开始时间: {self.start_time}")

    def execute_collection(self, collection_mode: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行数据采集（兼容性方法）

        Args:
            collection_mode: 采集模式配置

        Returns:
            Dict: 采集结果
        """
        try:
            # 使用现有的工作流方法
            account_config = self.config
            result = self.run_single_account_workflow(account_config)

            return {
                "success": result.success,
                "error": result.error_message if not result.success else None,
                "workflow_id": result.workflow_id,
                "duration": result.duration
            }

        except Exception as e:
            logger.error(f"[FAIL] 采集执行失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def run_single_account_workflow(self, account_config: Dict[str, Any]) -> AccountWorkflowResult:
        """
        运行单个账号的工作流
        
        Args:
            account_config: 账号配置
            
        Returns:
            AccountWorkflowResult: 工作流结果
        """
        workflow_start = datetime.now()
        steps = []
        
        try:
            logger.info(f"[RETRY] 开始账号工作流: {account_config.get('account_id', 'unknown')}")
            
            # 步骤1: 账号验证
            step1 = self._execute_step("account_validation", 
                                     lambda: self._validate_account(account_config))
            steps.append(step1)
            
            if step1.status == "failed":
                return self._create_failed_result(account_config, steps, workflow_start, step1.error)
            
            # 步骤2: 浏览器初始化
            step2 = self._execute_step("browser_initialization",
                                     lambda: self._initialize_browser(account_config))
            steps.append(step2)
            
            if step2.status == "failed":
                return self._create_failed_result(account_config, steps, workflow_start, step2.error)
            
            browser = step2.result["browser"]
            page = step2.result["page"]
            
            try:
                # 步骤3: 会话恢复
                step3 = self._execute_step("session_restoration",
                                         lambda: self._restore_session(page, account_config))
                steps.append(step3)
                
                # 步骤4: 登录验证
                if step3.status == "failed" or not step3.result.get("session_valid", False):
                    step4 = self._execute_step("login_verification",
                                             lambda: self._perform_login_verification(page, account_config))
                    steps.append(step4)
                    
                    if step4.status == "failed":
                        return self._create_failed_result(account_config, steps, workflow_start, step4.error)
                else:
                    # 会话有效，跳过登录
                    step4 = WorkflowStep(
                        name="login_verification",
                        status="completed",
                        start_time=datetime.now().isoformat(),
                        end_time=datetime.now().isoformat(),
                        duration=0.0,
                        result={"session_restored": True, "login_skipped": True}
                    )
                    steps.append(step4)
                
                # 步骤5: 页面分析
                step5 = self._execute_step("page_analysis",
                                         lambda: self._analyze_shopee_pages(page, account_config))
                steps.append(step5)
                
                if step5.status == "failed":
                    return self._create_failed_result(account_config, steps, workflow_start, step5.error)
                
                # 步骤6: 数据采集
                step6 = self._execute_step("data_collection",
                                         lambda: self._collect_shopee_data(page, account_config))
                steps.append(step6)
                
                if step6.status == "failed":
                    return self._create_failed_result(account_config, steps, workflow_start, step6.error)
                
                # 步骤7: 数据下载
                step7 = self._execute_step("data_download",
                                         lambda: self._download_shopee_data(page, account_config))
                steps.append(step7)
                
                if step7.status == "failed":
                    return self._create_failed_result(account_config, steps, workflow_start, step7.error)
                
                # 步骤8: 数据归总
                step8 = self._execute_step("data_consolidation",
                                         lambda: self._consolidate_account_data(account_config, 
                                                                              step6.result, 
                                                                              step7.result))
                steps.append(step8)
                
                if step8.status == "failed":
                    return self._create_failed_result(account_config, steps, workflow_start, step8.error)
                
                # 步骤9: 清理
                step9 = self._execute_step("cleanup",
                                         lambda: self._cleanup_resources(browser, page, account_config))
                steps.append(step9)
                
                # 创建工作流结果
                workflow_end = datetime.now()
                duration = (workflow_end - workflow_start).total_seconds()
                
                return AccountWorkflowResult(
                    account_id=account_config.get('account_id', ''),
                    store_name=account_config.get('store_name', ''),
                    workflow_id=self.workflow_id,
                    start_time=workflow_start.isoformat(),
                    end_time=workflow_end.isoformat(),
                    duration=duration,
                    steps=steps,
                    success=True,
                    data_files=step8.result.get("data_files", []),
                    analysis_files=step5.result.get("analysis_files", [])
                )
                
            finally:
                # 确保浏览器关闭
                if browser:
                    browser.close()
        
        except Exception as e:
            logger.error(f"[FAIL] 账号工作流执行失败: {e}")
            return self._create_failed_result(account_config, steps, workflow_start, str(e))
    
    def run_multi_account_workflow(self, account_configs: List[Dict[str, Any]], 
                                 max_workers: int = 3) -> MultiAccountWorkflowResult:
        """
        运行多账号并行工作流
        
        Args:
            account_configs: 账号配置列表
            max_workers: 最大并行数
            
        Returns:
            MultiAccountWorkflowResult: 多账号工作流结果
        """
        workflow_start = datetime.now()
        account_results = []
        successful_count = 0
        failed_count = 0
        
        logger.info(f"[START] 开始多账号工作流: {len(account_configs)} 个账号")
        
        try:
            # 使用线程池并行执行
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_account = {
                    executor.submit(self.run_single_account_workflow, account_config): account_config
                    for account_config in account_configs
                }
                
                # 收集结果
                for future in as_completed(future_to_account):
                    account_config = future_to_account[future]
                    try:
                        result = future.result()
                        account_results.append(result)
                        
                        if result.success:
                            successful_count += 1
                            logger.info(f"[OK] 账号 {result.account_id} 工作流完成")
                        else:
                            failed_count += 1
                            logger.error(f"[FAIL] 账号 {result.account_id} 工作流失败: {result.error_summary}")
                            
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"[FAIL] 账号 {account_config.get('account_id', 'unknown')} 工作流异常: {e}")
                        
                        # 创建失败结果
                        failed_result = AccountWorkflowResult(
                            account_id=account_config.get('account_id', ''),
                            store_name=account_config.get('store_name', ''),
                            workflow_id=self.workflow_id,
                            start_time=workflow_start.isoformat(),
                            end_time=datetime.now().isoformat(),
                            duration=(datetime.now() - workflow_start).total_seconds(),
                            steps=[],
                            success=False,
                            data_files=[],
                            analysis_files=[],
                            error_summary=str(e)
                        )
                        account_results.append(failed_result)
            
            # 生成汇总信息
            workflow_end = datetime.now()
            duration = (workflow_end - workflow_start).total_seconds()
            
            summary = self._generate_workflow_summary(account_results, duration)
            
            result = MultiAccountWorkflowResult(
                workflow_id=self.workflow_id,
                start_time=workflow_start.isoformat(),
                end_time=workflow_end.isoformat(),
                total_accounts=len(account_configs),
                successful_accounts=successful_count,
                failed_accounts=failed_count,
                account_results=account_results,
                summary=summary
            )
            
            # 保存工作流结果
            self._save_workflow_result(result)
            
            logger.info(f"[DONE] 多账号工作流完成")
            logger.info(f"   总账号数: {len(account_configs)}")
            logger.info(f"   成功账号: {successful_count}")
            logger.info(f"   失败账号: {failed_count}")
            logger.info(f"   总耗时: {duration:.2f}秒")
            
            return result
            
        except Exception as e:
            logger.error(f"[FAIL] 多账号工作流执行失败: {e}")
            raise
    
    def _execute_step(self, step_name: str, step_function) -> WorkflowStep:
        """执行工作流步骤"""
        step_start = datetime.now()
        step = WorkflowStep(
            name=step_name,
            status="running",
            start_time=step_start.isoformat()
        )
        
        try:
            logger.info(f"[RETRY] 执行步骤: {step_name}")
            result = step_function()
            
            step.status = "completed"
            step.end_time = datetime.now().isoformat()
            step.duration = (datetime.now() - step_start).total_seconds()
            step.result = result
            
            logger.info(f"[OK] 步骤完成: {step_name} (耗时: {step.duration:.2f}秒)")
            return step
            
        except Exception as e:
            step.status = "failed"
            step.end_time = datetime.now().isoformat()
            step.duration = (datetime.now() - step_start).total_seconds()
            step.error = str(e)
            
            logger.error(f"[FAIL] 步骤失败: {step_name} - {e}")
            return step
    
    def _validate_account(self, account_config: Dict[str, Any]) -> Dict[str, Any]:
        """验证账号配置"""
        required_fields = ['account_id', 'username', 'password', 'login_url']
        missing_fields = [field for field in required_fields if not account_config.get(field)]
        
        if missing_fields:
            raise ValueError(f"账号配置缺少必要字段: {missing_fields}")
        
        return {"valid": True, "account_id": account_config['account_id']}
    
    def _initialize_browser(self, account_config: Dict[str, Any]) -> Dict[str, Any]:
        """初始化浏览器"""
        playwright = sync_playwright().start()
        
        browser = playwright.chromium.launch(
            headless=self.config.get("headless", False),
            slow_mo=self.config.get("slow_mo", 1000)
        )
        
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        page = context.new_page()
        
        return {
            "browser": browser,
            "context": context,
            "page": page,
            "playwright": playwright
        }
    
    def _restore_session(self, page: Page, account_config: Dict[str, Any]) -> Dict[str, Any]:
        """恢复会话"""
        try:
            # 创建会话管理器
            session_manager = SessionManager()
            
            # 尝试恢复会话
            session_restored = session_manager.restore_session(page, account_config)
            
            if session_restored:
                # 验证会话是否有效
                page.goto(account_config['login_url'])
                time.sleep(3)
                
                # 检查是否已登录
                if self._is_logged_in(page):
                    return {"session_valid": True, "session_restored": True}
            
            return {"session_valid": False, "session_restored": session_restored}
            
        except Exception as e:
            logger.warning(f"[WARN] 会话恢复失败: {e}")
            return {"session_valid": False, "session_restored": False}
    
    def _is_logged_in(self, page: Page) -> bool:
        """检查是否已登录"""
        try:
            # 检查登录状态指示器
            login_indicators = [
                "div:has-text('退出')",
                "div:has-text('Logout')",
                "a:has-text('退出')",
                "a:has-text('Logout')",
                ".user-info",
                ".profile-menu"
            ]
            
            for indicator in login_indicators:
                if page.locator(indicator).count() > 0:
                    return True
            
            # 检查URL是否包含登录页面标识
            if "login" in page.url.lower() or "signin" in page.url.lower():
                return False
            
            return True
            
        except Exception:
            return False
    
    def _needs_verification(self, page: Page) -> bool:
        """检查是否需要验证码"""
        try:
            # 检查验证码输入框
            verification_indicators = [
                "input[placeholder*='验证码']",
                "input[placeholder*='OTP']",
                "input[placeholder*='Code']",
                "div:has-text('邮箱验证')",
                "div:has-text('OTP')"
            ]
            
            for indicator in verification_indicators:
                if page.locator(indicator).count() > 0:
                    return True
            
            return False
            
        except Exception:
            return False
    
    def _input_verification_code(self, page: Page, otp_code: str) -> bool:
        """输入验证码"""
        try:
            # 查找验证码输入框
            otp_input_selectors = [
                "input[placeholder*='验证码']",
                "input[placeholder*='OTP']",
                "input[placeholder*='Code']",
                "input[name='otp']",
                "input[name='verification_code']"
            ]
            
            for selector in otp_input_selectors:
                try:
                    otp_input = page.locator(selector)
                    if otp_input.count() > 0:
                        otp_input.fill(otp_code)
                        logger.info(f"[OK] 验证码已输入: {otp_code}")
                        
                        # 查找确认按钮
                        confirm_selectors = [
                            "button:has-text('确认')",
                            "button:has-text('验证')",
                            "button:has-text('Submit')",
                            "button[type='submit']"
                        ]
                        
                        for confirm_selector in confirm_selectors:
                            try:
                                confirm_button = page.locator(confirm_selector)
                                if confirm_button.count() > 0:
                                    confirm_button.click()
                                    logger.info("[OK] 验证码确认按钮已点击")
                                    return True
                            except Exception:
                                continue
                        
                        return True
                except Exception:
                    continue
            
            logger.warning("[WARN] 未找到验证码输入框或确认按钮")
            return False
            
        except Exception as e:
            logger.error(f"[FAIL] 输入验证码失败: {e}")
            return False
    
    def _perform_login_verification(self, page: Page, account_config: Dict[str, Any]) -> Dict[str, Any]:
        """执行登录验证"""
        try:
            logger.info(f"[LOCK] 开始登录验证: {account_config.get('account_id', '')}")
            
            # 首先访问登录页面
            login_url = account_config.get('login_url', 'https://seller.shopee.cn/account/signin')
            page.goto(login_url, timeout=30000)
            time.sleep(3)
            
            # 检查是否已经登录
            if self._is_logged_in(page):
                logger.info("[OK] 已登录，无需验证码")
                return {"login_success": True, "otp_used": False}
            
            # 创建Shopee采集器进行登录
            from .shopee_collector import ShopeeCollector
            collector = ShopeeCollector(account_config)
            collector.page = page
            
            # 执行登录流程
            login_result = collector.login()
            
            if login_result:
                logger.info("[OK] 登录成功")
                return {
                    "login_success": True,
                    "otp_used": True,
                    "provider": "shopee_collector"
                }
            else:
                # 检查是否需要验证码
                if self._needs_verification(page):
                    logger.info("[EMAIL] 检测到需要验证码，开始处理...")
                    
                    # 使用统一验证码服务
                    otp_code = self.verification_service.request_otp(
                        channel="email",
                        context=account_config,
                        timeout_seconds=120
                    )
                    
                    if otp_code:
                        logger.info(f"[OK] OTP获取成功: {otp_code}")
                        
                        # 输入验证码
                        if self._input_verification_code(page, otp_code):
                            logger.info("[OK] 验证码输入成功")
                            
                            # 等待验证结果
                            time.sleep(3)
                            
                            if self._is_logged_in(page):
                                return {
                                    "login_success": True,
                                    "otp_used": True,
                                    "otp_code": otp_code,
                                    "provider": "email"
                                }
                            else:
                                return {
                                    "login_success": False,
                                    "error": "验证码验证失败"
                                }
                        else:
                            return {
                                "login_success": False,
                                "error": "验证码输入失败"
                            }
                    else:
                        logger.warning("[WARN] OTP获取失败")
                        
                        # 尝试手动输入
                        logger.info("[TIP] 尝试手动输入验证码...")
                        manual_otp = self._get_manual_otp()
                        
                        if manual_otp and self._input_verification_code(page, manual_otp):
                            logger.info("[OK] 手动验证码输入成功")
                            time.sleep(3)
                            
                            if self._is_logged_in(page):
                                return {
                                    "login_success": True,
                                    "otp_used": True,
                                    "otp_code": manual_otp,
                                    "provider": "manual"
                                }
                        
                        return {
                            "login_success": False,
                            "error": "验证码处理失败"
                        }
                else:
                    return {
                        "login_success": False,
                        "error": "登录失败，原因未知"
                    }
            
        except Exception as e:
            logger.error(f"[FAIL] 登录验证失败: {e}")
            return {"login_success": False, "error": str(e)}
    
    def _analyze_shopee_pages(self, page: Page, account_config: Dict[str, Any]) -> Dict[str, Any]:
        """分析Shopee页面 - 仅在登录成功后执行"""
        try:
            # 首先确认已经登录
            if not self._is_logged_in(page):
                logger.error("[FAIL] 未登录状态，无法进行页面分析")
                return {"error": "未登录状态，无法进行页面分析"}
            
            logger.info("[SEARCH] 开始分析Shopee页面（已登录状态）")
            
            # 创建页面分析器
            analyzer = ShopeePageAnalyzer(page, account_config)
            
            # 分析平台（仅在登录状态下）
            analysis_result = analyzer.analyze_shopee_platform_logged_in()
            
            # 保存分析结果
            analysis_file = analyzer.save_analysis_result(analysis_result)
            
            # 生成报告
            report = analyzer.generate_shopee_report(analysis_result)
            report_file = self._save_analysis_report(report, account_config)
            
            return {
                "analysis_result": analysis_result,
                "analysis_files": [analysis_file, report_file],
                "available_sections": len(analysis_result.available_sections),
                "menu_structures": len(analysis_result.menu_structure),
                "download_capabilities": len(analysis_result.download_capabilities)
            }
            
        except Exception as e:
            logger.error(f"[FAIL] 页面分析失败: {e}")
            return {"error": str(e)}
    
    def _collect_shopee_data(self, page: Page, account_config: Dict[str, Any]) -> Dict[str, Any]:
        """采集Shopee数据"""
        try:
            # 创建Shopee采集器
            collector = ShopeeCollector(account_config)
            
            # 设置页面对象
            collector.page = page
            
            # 采集运营数据
            collection_result = collector.collect_operational_data()
            
            return {
                "collection_success": collection_result.get('success', False),
                "collected_data": collection_result.get('data', {}),
                "error": collection_result.get('error')
            }
            
        except Exception as e:
            logger.error(f"[FAIL] 数据采集失败: {e}")
            return {"collection_success": False, "error": str(e)}
    
    def _download_shopee_data(self, page: Page, account_config: Dict[str, Any]) -> Dict[str, Any]:
        """下载Shopee数据"""
        try:
            # 创建Shopee采集器
            collector = ShopeeCollector(account_config)
            
            # 设置页面对象
            collector.page = page
            
            # 下载数据报告
            download_success = collector.download_data_report()
            
            return {
                "download_success": download_success,
                "download_path": str(collector.downloads_path)
            }
            
        except Exception as e:
            logger.error(f"[FAIL] 数据下载失败: {e}")
            return {"download_success": False, "error": str(e)}
    
    def _consolidate_account_data(self, account_config: Dict[str, Any], 
                                collection_result: Dict[str, Any],
                                download_result: Dict[str, Any]) -> Dict[str, Any]:
        """归总账号数据"""
        try:
            account_id = account_config.get('account_id', '')
            store_name = account_config.get('store_name', '')
            
            # 创建账号专属目录
            account_dir = self.output_base / store_name
            account_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成数据汇总文件
            consolidation_data = {
                "account_info": {
                    "account_id": account_id,
                    "store_name": store_name,
                    "platform": "shopee",
                    "consolidation_time": datetime.now().isoformat()
                },
                "collection_result": collection_result,
                "download_result": download_result,
                "workflow_info": {
                    "workflow_id": self.workflow_id,
                    "version": "1.0.0"
                }
            }
            
            # 保存汇总文件
            consolidation_file = account_dir / f"consolidation_{account_id}_{int(time.time())}.json"
            with open(consolidation_file, 'w', encoding='utf-8') as f:
                json.dump(consolidation_data, f, ensure_ascii=False, indent=2)
            
            return {
                "consolidation_success": True,
                "data_files": [str(consolidation_file)],
                "account_dir": str(account_dir)
            }
            
        except Exception as e:
            logger.error(f"[FAIL] 数据归总失败: {e}")
            return {"consolidation_success": False, "error": str(e)}
    
    def _cleanup_resources(self, browser: Browser, page: Page, account_config: Dict[str, Any]) -> Dict[str, Any]:
        """清理资源"""
        try:
            if page:
                page.close()
            if browser:
                browser.close()
            
            return {"cleanup_success": True}
            
        except Exception as e:
            logger.warning(f"[WARN] 资源清理失败: {e}")
            return {"cleanup_success": False, "error": str(e)}
    
    def _create_failed_result(self, account_config: Dict[str, Any], steps: List[WorkflowStep], 
                            start_time: datetime, error: str) -> AccountWorkflowResult:
        """创建失败结果"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return AccountWorkflowResult(
            account_id=account_config.get('account_id', ''),
            store_name=account_config.get('store_name', ''),
            workflow_id=self.workflow_id,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration=duration,
            steps=steps,
            success=False,
            data_files=[],
            analysis_files=[],
            error_summary=error
        )
    
    def _save_analysis_report(self, report: str, account_config: Dict[str, Any]) -> str:
        """保存分析报告"""
        try:
            account_id = account_config.get('account_id', '')
            store_name = account_config.get('store_name', '')
            
            report_dir = self.output_base / store_name / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = report_dir / f"analysis_report_{account_id}_{timestamp}.txt"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            
            return str(report_file)
            
        except Exception as e:
            logger.error(f"[FAIL] 保存分析报告失败: {e}")
            return ""
    
    def _generate_workflow_summary(self, account_results: List[AccountWorkflowResult], 
                                 total_duration: float) -> Dict[str, Any]:
        """生成工作流汇总"""
        try:
            successful_results = [r for r in account_results if r.success]
            failed_results = [r for r in account_results if not r.success]
            
            summary = {
                "total_accounts": len(account_results),
                "successful_accounts": len(successful_results),
                "failed_accounts": len(failed_results),
                "success_rate": len(successful_results) / len(account_results) if account_results else 0,
                "total_duration": total_duration,
                "average_duration": sum(r.duration for r in account_results) / len(account_results) if account_results else 0,
                "total_data_files": sum(len(r.data_files) for r in account_results),
                "total_analysis_files": sum(len(r.analysis_files) for r in account_results),
                "error_summary": [r.error_summary for r in failed_results if r.error_summary]
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"[FAIL] 生成工作流汇总失败: {e}")
            return {}
    
    def _save_workflow_result(self, result: MultiAccountWorkflowResult) -> str:
        """保存工作流结果"""
        try:
            workflow_dir = self.output_base / "workflows"
            workflow_dir.mkdir(parents=True, exist_ok=True)
            
            workflow_file = workflow_dir / f"workflow_{self.workflow_id}.json"
            
            with open(workflow_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(result), f, ensure_ascii=False, indent=2)
            
            logger.info(f"[SAVE] 工作流结果已保存: {workflow_file}")
            return str(workflow_file)
            
        except Exception as e:
            logger.error(f"[FAIL] 保存工作流结果失败: {e}")
            return ""
    
    def _get_manual_otp(self) -> Optional[str]:
        """获取手动输入的OTP"""
        try:
            print("\n" + "="*60)
            print("[LOCK] 需要验证码")
            print("[EMAIL] 请检查您的邮箱获取验证码")
            print("[TIP] 如果长时间收不到验证码，可以尝试重新发送")
            print("="*60)
            
            manual_code = input("请输入验证码（4-8位数字）: ").strip()
            
            if manual_code and len(manual_code) >= 4:
                logger.info(f"用户手动输入验证码: {manual_code}")
                return manual_code
            else:
                logger.error("验证码输入无效")
                return None
                
        except Exception as e:
            logger.error(f"获取手动验证码异常: {e}")
            return None


def create_shopee_workflow_manager(config: Dict[str, Any] = None) -> ShopeeWorkflowManager:
    """
    创建Shopee工作流管理器
    
    Args:
        config: 工作流配置
        
    Returns:
        ShopeeWorkflowManager: 工作流管理器实例
    """
    return ShopeeWorkflowManager(config) 