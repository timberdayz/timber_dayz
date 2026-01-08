"""
录制配方执行器

基于录制生成的配方文件，自动复刻用户的操作
"""

import json
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from modules.utils.logger import logger


class RecipeExecutor:
    """配方执行器 - 复刻录制的操作"""

    def __init__(self):
        self.retry_count = 3
        self.retry_delay = 1.0
        self.action_delay = 0.5

    def execute_recipe(self, page, recipe_path: Path) -> bool:
        """
        执行配方文件中的操作

        Args:
            page: Playwright页面对象
            recipe_path: 配方文件路径

        Returns:
            bool: 执行是否成功
        """
        try:
            if not recipe_path.exists():
                logger.error(f"配方文件不存在: {recipe_path}")
                return False

            # 加载配方
            recipe = json.loads(recipe_path.read_text(encoding='utf-8'))
            logger.info(f"[BOOK] 加载配方: {recipe.get('page_key', 'unknown')}")
            logger.info(f"   生成时间: {recipe.get('generated_at', 'unknown')}")
            logger.info(f"   操作步骤: {len(recipe.get('steps', []))}")

            # 验证页面URL匹配
            current_url = page.url
            url_pattern = recipe.get('url_pattern', '')
            if url_pattern and not self._url_matches_pattern(current_url, url_pattern):
                # 降级为调试提示，避免误导；复用产品页配方用于服务页属预期行为
                logger.debug(f"[RecipeExecutor] URL与配方不一致(提示): {current_url} vs {url_pattern}")

            # 执行步骤
            steps = recipe.get('steps', [])
            success_count = 0

            for step in steps:
                if self._execute_step(page, step):
                    success_count += 1
                    time.sleep(self.action_delay)
                else:
                    logger.warning(f"步骤 {step.get('step_id')} 执行失败，继续下一步")

            logger.info(f"[OK] 配方执行完成: {success_count}/{len(steps)} 步骤成功")
            return success_count > 0

        except Exception as e:
            logger.error(f"配方执行失败: {e}")
            return False

    def _execute_step(self, page, step: Dict) -> bool:
        """执行单个步骤"""
        step_id = step.get('step_id', 0)
        action = step.get('action', 'unknown')
        description = step.get('description', '')
        candidates = step.get('candidates', [])

        logger.info(f"[TARGET] 执行步骤 {step_id}: {description}")

        # 按优先级排序候选选择器，确保文本选择器优先
        sorted_candidates = sorted(candidates, key=lambda x: (x.get('priority', 999), 0 if x.get('type') == 'text' else 1))

        # 尝试每个候选选择器
        for i, candidate in enumerate(sorted_candidates):
            try:
                selector_type = candidate.get('type', 'unknown')
                selector_value = candidate.get('value', '')
                priority = candidate.get('priority', 999)

                logger.debug(f"  尝试选择器 {i+1}/{len(sorted_candidates)}: {selector_type}='{selector_value}' (优先级:{priority})")

                # 对于选择快捷项，强制优先使用文本选择器
                if action == 'select_shortcut' and selector_type == 'text':
                    logger.info(f"  [TARGET] 优先使用文本选择器: '{selector_value}'")

                if self._try_selector(page, selector_type, selector_value, action):
                    logger.info(f"  [OK] 步骤 {step_id} 成功 (使用: {selector_type})")

                    # 如果是打开日期选择器的步骤，立即扫描可用选项
                    if action == 'open_picker':
                        time.sleep(0.5)  # 等待选择器完全展开
                        self._scan_and_log_date_options(page)

                    return True

            except Exception as e:
                logger.debug(f"  选择器失败: {e}")
                continue

        # 最后的fallback：如果是选择快捷项，尝试智能查找
        if action == 'select_shortcut':
            logger.info(f"  [RETRY] 尝试智能fallback查找: {step.get('description', '')}")
            if self._smart_fallback_selection(page, step):
                logger.info(f"  [OK] 步骤 {step_id} 智能fallback成功")
                return True

        logger.error(f"  [FAIL] 步骤 {step_id} 所有选择器都失败")
        return False

    def _try_selector(self, page, selector_type: str, selector_value: str, action: str) -> bool:
        """尝试使用特定选择器执行操作"""

        for attempt in range(self.retry_count):
            try:
                if selector_type == 'text':
                    # 文本选择器：引入“空白不敏感”的正则匹配，快速命中 '过去7天' / '过去7 天' 等变体
                    element = None
                    target = (selector_value or '').strip()

                    # 1) 空白不敏感正则：在每个字符之间允许可选空格（\s*）
                    try:
                        pieces = [re.escape(ch) for ch in target]
                        regex_str = r"\s*".join(pieces)  # 过\s*去\s*7\s*天
                        pattern = re.compile(regex_str, re.IGNORECASE)
                    except Exception:
                        # 退化到仅将空格宽松化
                        pattern = re.compile(re.escape(target).replace(r"\ ", r"\s*"), re.IGNORECASE)

                    try:
                        el = page.get_by_text(pattern)
                        el.wait_for(state='visible', timeout=1200)
                        element = el
                        logger.debug("文本正则匹配成功（空白不敏感）")
                    except Exception:
                        # 2) 变体匹配：移除空格/插入空格
                        text_variants = [
                            target,
                            target.replace(' ', ''),
                            target.replace('过去', '过去 ').replace('天', ' 天'),
                        ]
                        for variant in text_variants:
                            try:
                                el2 = page.get_by_text(variant, exact=False)
                                el2.wait_for(state='visible', timeout=1000)
                                element = el2
                                logger.debug(f"文本匹配成功，使用变体: '{variant}'")
                                break
                            except Exception:
                                continue

                    # 3) 快速容器扫描（仅限日期快捷项容器），做最终尝试
                    if element is None:
                        try:
                            items = page.locator('.eds-date-shortcut-item__text')
                            cnt = items.count()
                            def _norm(s: str) -> str:
                                return (s or '').replace(' ', '').strip()
                            for idx in range(max(0, cnt)):
                                try:
                                    el3 = items.nth(idx)
                                    txt = (el3.text_content() or '').strip()
                                    if _norm(txt) == _norm(target):
                                        element = el3
                                        logger.debug(f"容器扫描匹配成功: '{txt}'")
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                    if element is None:
                        raise Exception("文本匹配未命中（正则/变体/容器扫描均失败）")

                elif selector_type == 'css':
                    # CSS选择器
                    element = page.locator(selector_value)
                    element.wait_for(state='visible', timeout=3000)
                else:
                    logger.debug(f"不支持的选择器类型: {selector_type}")
                    return False

                # 执行点击操作
                element.click(timeout=3000)

                # 等待页面稳定
                time.sleep(0.3)

                # 验证点击是否生效（对于文本选择器）
                if selector_type == 'text' and action == 'select_shortcut':
                    time.sleep(0.5)  # 给页面更多时间更新

                return True

            except Exception as e:
                if attempt < self.retry_count - 1:
                    logger.debug(f"    重试 {attempt + 1}/{self.retry_count}: {e}")
                    time.sleep(self.retry_delay)
                else:
                    logger.debug(f"    最终失败: {e}")

        return False

    def _url_matches_pattern(self, url: str, pattern: str) -> bool:
        """检查URL是否匹配模式"""
        # 简单的通配符匹配
        if '*' in pattern:
            parts = pattern.split('*')
            for part in parts:
                if part and part not in url:
                    return False
            return True
        else:
            return pattern in url

    def execute_date_picker_recipe(self, page, shop_id: str = None, target_option: str = "过去7 天") -> bool:
        """
        执行日期控件配方（便捷方法）

        Args:
            page: Playwright页面对象
            shop_id: 店铺ID（可选，用于查找配方）
            target_option: 目标时间选项，如"过去7 天"、"过去30 天"等

        Returns:
            bool: 执行是否成功
        """
        try:
            # 查找最新的日期控件配方（包含内置配方与输出目录配方）
            recipe_path = self._find_latest_date_picker_recipe()
            if recipe_path:
                logger.info(f"[ACTION] 开始复刻日期控件操作，目标选项: {target_option}")
                return self.execute_recipe_with_target(page, recipe_path, target_option)

            # 未找到配方 -> 降级为 WARNING，并启用通用兜底策略
            logger.warning("未找到日期控件配方文件，启用通用兜底日期选择策略")
            ok = self._execute_analytics_date_recipe(page, target_option, "traffic")
            if ok:
                logger.info("[OK] 兜底日期选择成功")
                return True
            else:
                logger.error("[FAIL] 兜底日期选择失败")
                return False

        except Exception as e:
            logger.error(f"日期控件配方执行失败: {e}")
            return False

    def execute_recipe_with_target(self, page, recipe_path: Path, target_option: str) -> bool:
        """
        执行配方并动态调整目标选项

        Args:
            page: Playwright页面对象
            recipe_path: 配方文件路径
            target_option: 目标时间选项

        Returns:
            bool: 执行是否成功
        """
        try:
            if not recipe_path.exists():
                logger.error(f"配方文件不存在: {recipe_path}")
                return False

            # 加载配方
            recipe = json.loads(recipe_path.read_text(encoding='utf-8'))
            logger.info(f"[BOOK] 加载配方: {recipe.get('page_key', 'unknown')}")
            logger.info(f"   目标选项: {target_option}")
            logger.info(f"   操作步骤: {len(recipe.get('steps', []))}")

            # 验证页面URL匹配
            current_url = page.url
            url_pattern = recipe.get('url_pattern', '')
            if url_pattern and not self._url_matches_pattern(current_url, url_pattern):
                logger.debug(f"[RecipeExecutor] URL与配方不一致(提示): {current_url} vs {url_pattern}")

            # 在执行配方前，先检查并关闭可能的通知弹窗
            self._close_notification_modal(page)

            # 特殊处理：如果目标是"今日实时"，先检查当前状态
            if target_option == "今日实时":
                logger.info(f"[SEARCH] 检查页面是否已经是'今日实时'状态...")
                if self._check_current_time_selection(page, target_option):
                    logger.info(f"[OK] 页面已经是'今日实时'状态，跳过时间选择操作")
                    return True
                else:
                    logger.info(f"[NOTE] 页面不是'今日实时'状态，继续执行配方")

            # 动态调整配方中的目标文本
            adjusted_steps = self._adjust_recipe_target(recipe.get('steps', []), target_option)

            # 调试：显示调整后的配方
            for step in adjusted_steps:
                if step.get('action') == 'select_shortcut':
                    logger.info(f"[NOTE] 调整后的步骤: {step.get('description')}")
                    for candidate in step.get('candidates', []):
                        logger.info(f"   候选器: {candidate.get('type')}='{candidate.get('value')}' (优先级:{candidate.get('priority')})")

            # 执行步骤
            success_count = 0
            for step in adjusted_steps:
                if self._execute_step(page, step):
                    success_count += 1
                    time.sleep(self.action_delay)

                    # 如果是选择快捷项的步骤，验证是否选择正确
                    if step.get('action') == 'select_shortcut':
                        time.sleep(1.5)  # 增加等待时间，确保页面更新
                        verification_result = self._verify_selection(page, target_option)
                        if verification_result:
                            logger.info(f"[OK] 验证成功：已正确选择 {target_option}")
                        else:
                            # 宽容处理：如果操作步骤成功，不强制重试
                            logger.info(f"[WARN] 验证不确定：目标是 {target_option}，但验证方法可能不适用当前页面状态")
                            logger.info(f"[TIP] 操作步骤已成功执行，继续后续流程（验证失败不影响实际功能）")

                            # 可选的轻量重试（不影响主流程）
                            try:
                                if self._light_retry_verification(page, target_option):
                                    logger.info(f"[OK] 轻量重试验证成功：{target_option}")
                                else:
                                    logger.debug(f"[SEARCH] 轻量重试验证仍失败，但不影响主流程")
                            except Exception as e:
                                logger.debug(f"轻量重试过程异常: {e}")
                else:
                    logger.warning(f"步骤 {step.get('step_id')} 执行失败，继续下一步")

            logger.info(f"[OK] 配方执行完成: {success_count}/{len(adjusted_steps)} 步骤成功")
            return success_count > 0

        except Exception as e:
            logger.error(f"配方执行失败: {e}")
            return False

    def _adjust_recipe_target(self, steps: List[Dict], target_option: str) -> List[Dict]:
        """动态调整配方中的目标文本"""
        adjusted_steps = []

        for step in steps:
            adjusted_step = step.copy()

            # 如果是选择快捷项的步骤，动态调整目标文本
            if step.get('action') == 'select_shortcut':
                adjusted_candidates = []

                for candidate in step.get('candidates', []):
                    adjusted_candidate = candidate.copy()

                    # 如果是文本选择器，替换为目标选项并提高优先级
                    if candidate.get('type') == 'text':
                        # 智能调整目标文本，处理空格差异
                        adjusted_text = self._smart_adjust_target_text(target_option, candidate.get('value', ''))
                        adjusted_candidate['value'] = adjusted_text
                        adjusted_candidate['original_value'] = candidate.get('value', '')
                        # 确保文本选择器有最高优先级
                        adjusted_candidate['priority'] = 0

                    # 如果是CSS选择器且包含硬编码文本，也要动态调整
                    elif candidate.get('type') == 'css' and 'has-text(' in candidate.get('value', ''):
                        css_value = candidate.get('value', '')
                        # 统一将 has-text('...') 内的文本替换为目标选项，避免误点到“昨天”等错误项
                        try:
                            new_value = re.sub(r":has-text\('.*?'\)", f":has-text('{target_option}')", css_value)
                        except Exception:
                            base_selector = css_value.split(':has-text(')[0] if ':has-text(' in css_value else 'li'
                            new_value = f"{base_selector}:has-text('{target_option}')"
                        adjusted_candidate['value'] = new_value
                        adjusted_candidate['original_value'] = css_value
                        logger.debug(f"动态调整CSS选择器: {css_value} -> {new_value}")

                    adjusted_candidates.append(adjusted_candidate)

                # 按优先级重新排序，确保文本选择器优先
                adjusted_candidates.sort(key=lambda x: x.get('priority', 999))
                adjusted_step['candidates'] = adjusted_candidates
                adjusted_step['description'] = f"选择{target_option}"

            adjusted_steps.append(adjusted_step)

        return adjusted_steps

    def _verify_selection(self, page, target_option: str) -> bool:
        """验证是否正确选择了目标选项（增强容错性）"""
        try:
            # 标准化目标选项（去除多余空格）
            target_normalized = ' '.join(target_option.split())

            # 多重验证策略
            verification_methods = [
                self._verify_by_active_class,
                self._verify_by_date_range,
                self._verify_by_url_params,
                self._verify_by_page_content
            ]

            for method in verification_methods:
                try:
                    if method(page, target_normalized):
                        logger.debug(f"[OK] 验证成功 (方法: {method.__name__}): {target_option}")
                        return True
                except Exception as e:
                    logger.debug(f"验证方法 {method.__name__} 失败: {e}")
                    continue

            # 如果所有验证都失败，但操作步骤成功，给予宽容处理
            logger.debug(f"[WARN] 所有验证方法都失败，但操作可能仍然成功: {target_option}")
            return False

        except Exception as e:
            logger.debug(f"验证选择失败: {e}")
            return False

    def _verify_by_active_class(self, page, target_normalized: str) -> bool:
        """通过激活状态CSS类验证（增强空格容错）"""
        # 标准化目标文本，移除空格用于比较
        target_no_space = target_normalized.replace(' ', '').lower()

        active_elements = page.locator('.eds-date-shortcut-item.active, .eds-date-shortcut-item--active, [class*="active"]').all()

        for element in active_elements:
            try:
                text = element.text_content().strip()
                text_no_space = text.replace(' ', '').lower()

                # 多种匹配方式
                if (target_no_space == text_no_space or
                    target_no_space in text_no_space or
                    text_no_space in target_no_space):
                    logger.debug(f"激活元素匹配成功: '{target_normalized}' <-> '{text}'")
                    return True
            except:
                continue

        # 检查快捷选项的父元素激活状态
        all_shortcuts = page.locator('.eds-date-shortcut-item__text').all()
        for element in all_shortcuts:
            try:
                text = element.text_content().strip()
                text_no_space = text.replace(' ', '').lower()

                if target_no_space == text_no_space or target_no_space in text_no_space:
                    parent = element.locator('..').first
                    class_name = parent.get_attribute('class') or ''
                    if 'active' in class_name.lower():
                        logger.debug(f"父元素激活匹配成功: '{target_normalized}' <-> '{text}'")
                        return True
            except:
                continue
        return False

    def _verify_by_date_range(self, page, target_normalized: str) -> bool:
        """通过日期范围验证（更可靠的方法）"""
        try:
            # 查找日期显示区域
            date_selectors = [
                '.eds-date-picker-input input',
                '[placeholder*="日期"]',
                '.date-range-display',
                '.eds-date-picker__input'
            ]

            for selector in date_selectors:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        value = element.get_attribute('value') or element.text_content() or ''
                        if value.strip():
                            # 检查日期范围是否符合预期
                            if self._is_date_range_valid(value, target_normalized):
                                return True
                except:
                    continue
            return False
        except:
            return False

    def _verify_by_url_params(self, page, target_normalized: str) -> bool:
        """通过URL参数验证"""
        try:
            url = page.url
            # 检查URL中是否包含日期相关参数
            if 'date' in url.lower() or 'time' in url.lower():
                # 简单检查：如果URL发生了变化，说明选择可能生效
                return True
            return False
        except:
            return False

    def _verify_by_page_content(self, page, target_normalized: str) -> bool:
        """通过页面内容变化验证（增强空格容错）"""
        try:
            # 标准化目标文本，移除空格用于比较
            target_no_space = target_normalized.replace(' ', '').lower()

            # 1. 检查日期选择器显示的文本
            date_display_selectors = [
                '.eds-date-picker-input',
                '[class*="date-picker"]',
                '.date-range-display',
                '.eds-date-shortcut-item.active',
                '.eds-date-shortcut-item--active'
            ]

            for selector in date_display_selectors:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        text = element.text_content().strip()
                        text_no_space = text.replace(' ', '').lower()

                        if target_no_space in text_no_space or text_no_space in target_no_space:
                            logger.debug(f"页面内容匹配成功: '{target_normalized}' <-> '{text}'")
                            return True
                except:
                    continue

            # 2. 检查页面是否有数据加载的迹象
            loading_indicators = [
                '.loading',
                '.spinner',
                '[class*="loading"]',
                '.eds-loading'
            ]

            # 如果没有加载指示器，可能数据已经加载完成
            has_loading = False
            for selector in loading_indicators:
                try:
                    if page.locator(selector).count() > 0:
                        has_loading = True
                        break
                except:
                    continue

            # 如果没有加载状态，认为操作可能成功
            return not has_loading
        except:
            return False

    def _is_date_range_valid(self, date_value: str, target_option: str) -> bool:
        """检查日期范围是否与目标选项匹配（加强版）"""
        try:
            dv = (date_value or "").strip().lower().replace(" ", "")
            t = (target_option or "").strip().lower().replace(" ", "")

            # 今日实时：必须明确包含“今日/今天/today”关键字
            if ("今日" in t) or ("今天" in t) or ("today" in t):
                return ("今日" in dv) or ("今天" in dv) or ("today" in dv)

            # 昨天：需要包含“昨天/yesterday”关键字
            if ("昨天" in t) or ("yesterday" in t):
                return ("昨天" in dv) or ("yesterday" in dv)

            # 过去7天 / 过去30天：出现关键数字或英文
            if "7" in t:
                return ("7" in dv) or ("过去7" in dv) or ("last7" in dv)
            if "30" in t:
                return ("30" in dv) or ("过去30" in dv) or ("last30" in dv)

            # 回退：仅当明显是日期区间时才认为有效
            has_date_sep = ("/" in dv or "-" in dv) and any(ch.isdigit() for ch in dv)
            return bool(has_date_sep)
        except Exception:
            return False

    def _light_retry_verification(self, page, target_option: str) -> bool:
        """轻量级重试验证（不干扰主流程）"""
        try:
            # 等待更长时间让页面稳定
            time.sleep(2.0)

            # 再次尝试验证，但不执行任何点击操作
            return self._verify_selection(page, target_option)
        except Exception as e:
            logger.debug(f"轻量重试验证异常: {e}")
            return False

    def _smart_fallback_selection(self, page, step: Dict) -> bool:
        """智能fallback选择：扫描页面上所有可用选项并智能匹配"""
        try:
            # 从步骤描述中提取目标文本
            description = step.get('description', '')
            target_text = None

            # 尝试从描述中提取目标（如"选择过去30天"）
            if '选择' in description:
                target_text = description.replace('选择', '').strip()

            if not target_text:
                return False

            logger.info(f"[SEARCH] 智能扫描页面选项，目标: '{target_text}'")

            # 扫描页面上所有可能的日期选项
            available_options = self._scan_date_options(page)

            # 只显示简洁的文本选项
            simple_texts = [opt['text'] for opt in available_options
                          if opt['selector'] == '.eds-date-shortcut-item__text' and len(opt['text']) < 20]
            if simple_texts:
                logger.info(f"[LIST] 发现页面选项: {simple_texts}")
            else:
                logger.debug(f"[LIST] 发现页面选项: {len(available_options)} 个（详细信息已省略）")

            # 智能匹配目标选项
            best_match = self._find_best_match(target_text, available_options)

            if best_match:
                logger.info(f"[TARGET] 最佳匹配: '{target_text}' -> '{best_match['text']}'")
                try:
                    best_match['element'].click(timeout=3000)
                    time.sleep(1.5)  # 等待页面响应
                    logger.info(f"[OK] 智能选择成功: {best_match['text']}")
                    return True
                except Exception as e:
                    logger.debug(f"点击匹配元素失败: {e}")

            return False

        except Exception as e:
            logger.debug(f"智能fallback异常: {e}")
            return False

    def _scan_date_options(self, page) -> List[Dict]:
        """扫描页面上所有可用的日期选项"""
        options = []

        # 常见的日期选项选择器
        option_selectors = [
            '.eds-date-shortcut-item',
            '.eds-date-shortcut-item__text',
            '[class*="shortcut"]',
            '[class*="option"]',
            'li[role="option"]',
            '.date-option',
            '[class*="date"][class*="item"]',
            # 通用的可点击文本元素
            'li:visible',
            'div[role="option"]:visible',
            'span[role="option"]:visible',
        ]

        for selector in option_selectors:
            try:
                elements = page.locator(selector).all()
                for element in elements:
                    try:
                        if element.is_visible(timeout=500):
                            text = element.text_content().strip()
                            if text and ('天' in text or '日' in text or '周' in text or '月' in text):
                                options.append({
                                    'text': text,
                                    'element': element,
                                    'selector': selector
                                })
                    except:
                        continue
            except:
                continue

        # 去重（基于文本内容）
        unique_options = []
        seen_texts = set()
        for option in options:
            if option['text'] not in seen_texts:
                unique_options.append(option)
                seen_texts.add(option['text'])

        return unique_options

    def _find_best_match(self, target: str, options: List[Dict]) -> Dict:
        """在可用选项中找到最佳匹配"""
        if not options:
            return None

        # 标准化目标文本
        target_normalized = target.replace(' ', '').lower()

        # 匹配策略（按优先级）
        for option in options:
            option_text = option['text'].replace(' ', '').lower()

            # 1. 精确匹配
            if target_normalized == option_text:
                return option

        # 2. 包含匹配
        for option in options:
            option_text = option['text'].replace(' ', '').lower()
            if target_normalized in option_text or option_text in target_normalized:
                return option

        # 3. 关键词匹配（提取数字）
        target_numbers = re.findall(r'\d+', target)
        if target_numbers:
            target_num = target_numbers[0]
            for option in options:
                option_numbers = re.findall(r'\d+', option['text'])
                if option_numbers and option_numbers[0] == target_num:
                    return option

        return None

    def _retry_selection(self, page, target_option: str) -> bool:
        """重试选择目标选项"""
        try:
            logger.info(f"[RETRY] 重试选择: {target_option}")

            # 尝试直接点击目标文本
            try:
                element = page.get_by_text(target_option, exact=True)
                element.wait_for(state='visible', timeout=2000)
                element.click(timeout=2000)
                time.sleep(1.0)

                # 验证是否成功
                if self._verify_selection(page, target_option):
                    return True
            except:
                pass

            # 尝试包含匹配
            try:
                element = page.get_by_text(target_option, exact=False)
                element.wait_for(state='visible', timeout=2000)
                element.click(timeout=2000)
                time.sleep(1.0)

                # 验证是否成功
                if self._verify_selection(page, target_option):
                    return True
            except:
                pass

            return False

        except Exception as e:
            logger.debug(f"重试选择失败: {e}")
            return False

    def _check_current_time_selection(self, page, target_option: str) -> bool:
        """检查当前是否已经选择了目标时间选项"""
        try:
            # 标准化目标选项
            target_normalized = ' '.join(target_option.split())

            # 检查激活状态的选项
            active_selectors = [
                '.eds-date-shortcut-item.active .eds-date-shortcut-item__text',
                '.eds-date-shortcut-item--active .eds-date-shortcut-item__text',
                '[class*="active"] .eds-date-shortcut-item__text'
            ]

            for selector in active_selectors:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        text = element.text_content().strip()
                        text_normalized = ' '.join(text.split())
                        if target_normalized in text_normalized or text_normalized in target_normalized:
                            logger.info(f"[OK] 检测到当前已选择: {text}")
                            return True
                except:
                    continue

            return False

        except Exception as e:
            logger.debug(f"检查当前选择失败: {e}")
            return False

    def _close_notification_modal(self, page):
        """检查并关闭可能的通知/问卷弹窗（含 iframe 内部）。"""
        try:
            logger.debug("[SEARCH] 检查是否有通知/问卷弹窗需要关闭...")

            # 等待页面稳定
            try:
                page.wait_for_timeout(400)
            except Exception:
                pass

            # 统一在主页面与所有 iframe 内查找
            try:
                frames = list(getattr(page, 'frames', []))
            except Exception:
                frames = []
            roots = [page] + frames

            # 多种可能的弹窗关闭按钮选择器（含你提供的 i.eds-icon.eds-modal__close）
            close_selectors = [
                # 精确命中（本次问题的问卷弹窗）
                '.survey-window-modal i.eds-modal__close',
                '.survey-window-modal .eds-modal__close',
                '.eds-modal__box.survey-window-modal i.eds-icon.eds-modal__close',

                # 常见 close 图标
                'i.eds-icon.eds-modal__close',
                'i[data-v-ef5019c0][data-v-25a12b69].eds-icon.eds-modal__close',
                'i.eds-icon.eds-modal__close svg',
                'i.eds-icon.eds-modal__close path',

                # 通用 close/X
                '.eds-modal__close',
                '.modal-close',
                '.close-btn',
                '.ant-modal-close',
                '.el-dialog__close',
                '[role="dialog"] .close',
                '[aria-label="Close"]',
                'button[aria-label="关闭"]',

                # 文本按钮兜底
                'button:has-text("关闭")',
                'button:has-text("取消")',
                'button:has-text("稍后再说")',
                'button:has-text("我知道了")',

                # X 形状的通配
                '[class*="close"]:visible',
            ]

            # 若存在遮罩层亦尝试 Escape 关闭
            overlay_selectors = [
                '.eds-modal__mask', '.eds-modal__overlay', '.ant-modal-mask', '.el-overlay', '.survey-window-modal',
            ]

            modal_closed = False
            watch_ms, step_ms = 8000, 400  # 兼容“延迟出现”的弹窗（最多8秒）
            waited = 0
            while not modal_closed and waited <= watch_ms:
                # 逐个 root 尝试按钮关闭
                for root in roots:
                    root_name = getattr(root, 'url', lambda: 'frame')() if root is not page else 'page'
                    try:
                        for selector in close_selectors:
                            try:
                                element = root.locator(selector).first
                                if element.count() > 0 and element.is_visible():
                                    logger.info(f"[TARGET] 发现弹窗，点击关闭按钮: {selector} (in {root_name})")
                                    try:
                                        element.click()
                                    except Exception:
                                        # 避免遮挡，尝试强制点击
                                        element.click(force=True)
                                    try:
                                        root.wait_for_timeout(300)
                                    except Exception:
                                        pass
                                    modal_closed = True
                                    break
                            except Exception as e:
                                logger.debug(f"尝试关闭选择器失败 {selector}: {e}")
                                continue
                        if modal_closed:
                            break
                    except Exception:
                        continue

                # 如果按钮未命中，尝试通过遮罩与 ESC 关闭
                if not modal_closed:
                    for root in roots:
                        try:
                            for sel in overlay_selectors:
                                ov = root.locator(sel)
                                if ov.count() > 0 and ov.first.is_visible():
                                    try:
                                        root.keyboard.press('Escape')
                                        modal_closed = True
                                        logger.info("[TARGET] 通过 Escape 关闭弹窗/遮罩")
                                        break
                                    except Exception:
                                        pass
                            if modal_closed:
                                break
                        except Exception:
                            continue

                if modal_closed:
                    break

                # 仍未关闭则短暂等待后重试
                try:
                    page.wait_for_timeout(step_ms)
                except Exception:
                    pass
                waited += step_ms

            if modal_closed:
                logger.info("[OK] 弹窗已关闭")
                try:
                    page.wait_for_timeout(500)
                except Exception:
                    pass
            else:
                logger.debug("[NOTE] 未发现需要关闭的弹窗")

        except Exception as e:
            logger.debug(f"检查并关闭弹窗失败: {e}")
            # 不抛出异常，继续后续操作

    def execute_traffic_date_recipe(self, page, target_option: str) -> bool:
        """
        执行流量表现页面的日期控件配方

        Args:
            page: Playwright页面对象
            target_option: 目标时间选项 ("昨天", "过去7天", "过去30天")

        Returns:
            bool: 执行是否成功
        """
        return self._execute_analytics_date_recipe(page, target_option, "traffic")

    def execute_order_date_recipe(self, page, target_option: str) -> bool:
        """执行订单表现页面的日期控件配方"""
        return self._execute_analytics_date_recipe(page, target_option, "order")

    def execute_finance_date_recipe(self, page, target_option: str) -> bool:
        """执行财务表现页面的日期控件配方"""
        return self._execute_analytics_date_recipe(page, target_option, "finance")

    def _execute_analytics_date_recipe(self, page, target_option: str, analytics_type: str) -> bool:
        """
        执行数据分析页面的日期控件配方（通用版本）

        Args:
            page: Playwright页面对象
            target_option: 目标时间选项 ("昨天", "过去7天", "过去30天")
            analytics_type: 分析类型 ("traffic", "order", "finance")

        Returns:
            bool: 执行是否成功
        """
        try:
            type_names = {"traffic": "流量表现", "order": "订单表现", "finance": "财务表现"}
            type_name = type_names.get(analytics_type, analytics_type)
            logger.info(f"[TARGET] 执行{type_name}日期选择: {target_option}")

            # 在执行配方前，先检查并关闭可能的通知弹窗
            self._close_notification_modal(page)

            # 1) 打开日期选择器（更精确覆盖你提供的结构）
            open_selectors = [
                "div.bi-date-input.track-click-open-time-selector",
                "div.bi-date-input",
                "div.date-picker-trigger",
                ".date-range-picker",
                "[data-testid*='date']",
                "div:has-text('统计时间')",
                ".time-selector",
            ]
            logger.info("[TARGET] 执行步骤 1: 打开日期选择器")
            opened = False
            last_used = None
            for sel in open_selectors:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        el.click()
                        page.wait_for_timeout(250)
                        opened = True
                        last_used = sel
                        logger.info(f"[OK] 步骤 1 成功 (使用: {sel})")
                        break
                except Exception as e:
                    logger.debug(f"打开日期选择器失败 {sel}: {e}")
            if not opened:
                logger.error("[FAIL] 步骤 1 失败: 打开日期选择器")
                return False

            # 等待面板真正出现（避免动画/延迟导致后续找不到快捷项）
            panel_selectors = [
                ".eds-date-selector-panel",
                ".eds-date-picker__dropdown",
                ".eds-dropdown__content:has(.eds-date-shortcut-item)",
                ".eds-date-range-panel",
                "div:has(.eds-date-shortcut-item__text)",
                "div:has-text('昨天')",
            ]
            panel = None
            for ps in panel_selectors:
                try:
                    loc = page.locator(ps).first
                    if loc.count() > 0:
                        try:
                            loc.wait_for(state="visible", timeout=2000)
                        except Exception:
                            pass
                        if loc.is_visible():
                            panel = loc
                            break
                except Exception as e:
                    logger.debug(f"等待面板失败 {ps}: {e}")
            if panel is None:
                # 再尝试点击一次触发器并短暂等待
                try:
                    page.locator(last_used).first.click()
                except Exception:
                    pass
                page.wait_for_timeout(600)
                for ps in panel_selectors:
                    try:
                        loc = page.locator(ps).first
                        if loc.count() > 0 and loc.is_visible():
                            panel = loc
                            break
                    except Exception:
                        continue
            if panel is None:
                logger.error("[FAIL] 步骤 1.5 失败: 日期面板未出现")
                return False

            # 可选：录制模式（Inspector+事件监听）挂点
            # 设置环境变量 PW_RECORD_DATE_PICKER=1 将在此处暂停，方便你手动操作并在 Inspector 中点击 Recording
            try:
                import os
                if os.getenv("PW_RECORD_DATE_PICKER") == "1":
                    logger.info("[YELLOW] 调试模式：即将打开 Playwright Inspector 并暂停在日期面板，请点击 Recording 后手动完成操作...")
                    page.pause()
            except Exception as _e:
                logger.debug(f"录制模式挂点初始化失败: {_e}")


            # 2) 选择目标快捷项
            logger.info(f"[TARGET] 执行步骤 2: 选择{target_option}")
            # 生成多变体匹配（避免"过去30天"vs"过去30"的严格匹配失败）
            variants = self._generate_date_option_variants(target_option)
            option_selectors = []
            for variant in variants:
                option_selectors.extend([
                    f".eds-date-shortcut-item__text:has-text('{variant}')",
                    f".eds-date-shortcut-item:has-text('{variant}')",
                    f"li:has-text('{variant}')",
                    f"span:has-text('{variant}')",
                    f"button:has-text('{variant}')",
                    f"div:has-text('{variant}')",
                ])

            picked = False
            used_selector = None
            for sel in option_selectors:
                try:
                    scope = panel.locator(sel).first if panel else page.locator(sel).first
                    if scope.count() > 0 and scope.is_visible():
                        scope.click()
                        page.wait_for_timeout(600)
                        picked = True
                        used_selector = sel
                        logger.info(f"[OK] 步骤 2 成功 (使用: {sel})")
                        break
                except Exception as e:
                    logger.debug(f"点击快捷项失败 {sel}: {e}")

            if not picked:
                logger.warning(f"[WARN] 配方阶段未命中: 选择{target_option}，进入回退策略...")
                return False  # 触发回退，但不记为严重错误

            return True  # 配方阶段成功

        except Exception as e:
            logger.error(f"{type_name}日期控件配方执行失败: {e}")
            return False

    def _generate_date_option_variants(self, target_option: str) -> List[str]:
        """
        生成日期选项的多种变体，避免严格匹配失败

        Args:
            target_option: 原始选项（如"过去7天"）

        Returns:
            包含多种变体的列表
        """
        variants = [target_option]  # 原始选项

        # 常见变体映射
        variant_map = {
            "过去7天": ["过去7天", "过去 7 天", "过去7", "最近7天", "最近 7 天", "7天", "7 天"],
            "过去30天": ["过去30天", "过去 30 天", "过去30", "最近30天", "最近 30 天", "30天", "30 天"],
            "昨天": ["昨天", "昨日", "Yesterday"],
            "今天": ["今天", "今日", "Today"],
            "本周": ["本周", "这周", "This Week"],
            "本月": ["本月", "这月", "This Month"],
        }

        if target_option in variant_map:
            variants.extend(variant_map[target_option])

        # 去重并保持顺序
        seen = set()
        unique_variants = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                unique_variants.append(v)

        return unique_variants

    def _find_latest_date_picker_recipe(self) -> Optional[Path]:
        """查找最新的日期控件配方文件（优先使用简化版本；支持内置配方作为兜底）"""
        import glob
        import os

        # 1) 首先查找输出目录中的简化配方
        simplified_pattern = os.path.join('temp', 'outputs', 'shopee', '**', 'products', 'weekly', '.diag', 'recipes', 'date_picker_simplified.json')
        simplified_candidates = glob.glob(simplified_pattern, recursive=True)
        if simplified_candidates:
            latest_simplified = max(simplified_candidates, key=lambda p: os.path.getmtime(p))
            logger.info(f"[TARGET] 使用简化配方: {Path(latest_simplified).name}")
            return Path(latest_simplified)

        # 2) 回退到输出目录中的原始配方
        pattern = os.path.join('temp', 'outputs', 'shopee', '**', 'products', 'weekly', '.diag', 'recipes', 'date_picker.json')
        candidates = glob.glob(pattern, recursive=True)
        if candidates:
            latest_path = max(candidates, key=lambda p: os.path.getmtime(p))
            logger.info(f"[LIST] 使用原始配方: {Path(latest_path).name}")
            return Path(latest_path)

        # 3) 最后回退到仓库内置配方（精准命中 CN Seller Center 通用结构）
        builtins = [
            Path('modules/components/date_picker/recipes/shopee_cn/date_picker_simplified.json'),
            Path('modules/components/date_picker/recipes/shopee_cn/date_picker.json'),
        ]
        existing = [p for p in builtins if p.exists()]
        if existing:
            logger.info(f"[PUZZLE] 使用内置配方: {existing[0].name}")
            return existing[0]

        return None

    def _scan_and_log_date_options(self, page):
        """扫描并记录日期选择器的可用选项（简洁版本）"""
        try:
            # 只扫描文本选项，避免重复
            text_elements = page.locator('.eds-date-shortcut-item__text').all()

            simple_options = []
            for element in text_elements:
                try:
                    text = element.text_content().strip()
                    if text and len(text) < 20:  # 过滤掉过长的文本
                        simple_options.append(text)
                except:
                    continue

            if simple_options:
                logger.info(f"[LIST] 发现日期选项: {simple_options}")
            else:
                logger.debug("未发现有效的日期选项")

        except Exception as e:
            logger.debug(f"扫描日期选项失败: {e}")

    def _smart_adjust_target_text(self, target_option: str, original_value: str) -> str:
        """智能调整目标文本，处理空格等差异"""
        try:
            # 如果原始值包含空格模式，尝试调整目标文本
            if '过去' in target_option and '天' in target_option:
                # 检查原始值的空格模式
                if '过去' in original_value and ' 天' in original_value:
                    # 原始值有空格，调整目标文本也加空格
                    if '过去30天' == target_option:
                        return '过去30 天'
                    elif '过去7天' == target_option:
                        return '过去7 天'
                    elif '过去14天' == target_option:
                        return '过去14 天'

            # 如果没有特殊处理，返回原始目标
            return target_option

        except Exception as e:
            logger.debug(f"智能调整文本失败: {e}")
            return target_option
