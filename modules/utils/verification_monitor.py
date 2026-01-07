#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
动态验证码实时状态监控界面
提供用户友好的验证码处理过程监控和交互
"""

import streamlit as st
import time
import threading
from typing import Dict, Any
from datetime import datetime
import json


class VerificationMonitor:
    """验证码处理监控器"""
    
    def __init__(self):
        self.current_handler = None
        self.monitoring_active = False
        self.status_history = []
        
    def create_monitoring_interface(self, verification_handler):
        """创建监控界面"""
        self.current_handler = verification_handler
        
        st.title("🔐 智能验证码处理监控中心")
        st.markdown("---")
        
        # 状态概览区域
        self._render_status_overview()
        
        # 实时状态区域
        col1, col2 = st.columns([2, 1])
        
        with col1:
            self._render_real_time_status()
            
        with col2:
            self._render_control_panel()
        
        # 用户指引区域
        self._render_user_guidance()
        
        # 性能统计区域
        with st.expander("📊 性能统计", expanded=False):
            self._render_performance_stats()
    
    def _render_status_overview(self):
        """渲染状态概览"""
        if self.current_handler:
            status = self.current_handler.get_current_status()
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    label="当前状态",
                    value=self._get_status_display(status['state']),
                    delta=f"第 {status['attempt_count']} 次尝试"
                )
            
            with col2:
                popup_status = "已检测" if status['popup_detected'] else "未检测"
                st.metric(
                    label="弹窗检测",
                    value=popup_status,
                    delta="✅" if status['popup_detected'] else "❌"
                )
            
            with col3:
                st.metric(
                    label="处理时间",
                    value=f"{len(self.status_history)}s",
                    delta="实时"
                )
            
            with col4:
                error_status = "正常" if not status['last_error'] else "异常"
                st.metric(
                    label="系统状态", 
                    value=error_status,
                    delta="🟢" if not status['last_error'] else "🔴"
                )
    
    def _render_real_time_status(self):
        """渲染实时状态"""
        st.subheader("📊 实时状态监控")
        
        if self.current_handler:
            status = self.current_handler.get_current_status()
            
            # 状态进度条
            progress_value = self._get_progress_value(status['state'])
            st.progress(progress_value / 100)
            
            # 当前状态显示
            state_color = self._get_state_color(status['state'])
            st.markdown(f"""
            <div style="padding: 10px; border-radius: 5px; background-color: {state_color}; margin: 10px 0;">
                <h4>🔄 {self._get_status_display(status['state'])}</h4>
                <p>尝试次数: {status['attempt_count']}</p>
                {f'<p style="color: red;">❌ 错误: {status["last_error"]}</p>' if status['last_error'] else ''}
            </div>
            """, unsafe_allow_html=True)
            
            # 状态历史
            if self.status_history:
                st.subheader("📈 状态历史")
                history_data = []
                for i, record in enumerate(self.status_history[-10:]):
                    history_data.append({
                        "时间": record['timestamp'],
                        "状态": record['state'],
                        "描述": record['description']
                    })
                st.table(history_data)
    
    def _render_control_panel(self):
        """渲染控制面板"""
        st.subheader("🎮 控制面板")
        
        # 开始/停止监控按钮
        if st.button("▶️ 开始处理"):
            self._start_processing()
        
        if st.button("⏹️ 停止监控"):
            self.monitoring_active = False
            st.success("监控已停止")
        
        if st.button("🔄 刷新状态"):
            st.rerun()
        
        # 手动操作选项
        st.markdown("---")
        st.markdown("**🛠️ 手动操作**")
        
        if st.button("📧 手动发送邮箱验证码"):
            st.info("请在浏览器中手动点击'发送至邮箱'按钮")
        
        if st.button("✅ 确认验证码已输入"):
            if self.current_handler:
                # 强制进入确认状态
                st.success("系统将检测验证码并自动点击确认按钮")
    
    def _render_user_guidance(self):
        """渲染用户指引"""
        if self.current_handler:
            status = self.current_handler.get_current_status()
            
            if status['user_guidance']:
                st.subheader("📋 用户操作指引")
                
                # 美化指引显示
                st.markdown(f"""
                <div style="background-color: #e8f4f8; padding: 20px; border-radius: 10px; border-left: 5px solid #1f77b4;">
                    <pre style="white-space: pre-wrap; font-family: inherit;">{status['user_guidance']}</pre>
                </div>
                """, unsafe_allow_html=True)
                
                # 添加操作完成确认
                if st.button("✅ 我已完成上述操作"):
                    st.success("系统将继续自动处理...")
                    self._trigger_continue_processing()
    
    def _render_performance_stats(self):
        """渲染性能统计"""
        if self.current_handler:
            stats = self.current_handler.get_performance_stats()
            
            st.subheader("📊 选择器成功率统计")
            
            if stats['selector_stats']:
                selector_data = []
                for selector, data in stats['selector_stats'].items():
                    success_rate = (data['success'] / data['total']) * 100 if data['total'] > 0 else 0
                    selector_data.append({
                        "选择器": selector[:50] + "..." if len(selector) > 50 else selector,
                        "成功次数": data['success'],
                        "总次数": data['total'],
                        "成功率": f"{success_rate:.1f}%"
                    })
                
                st.table(selector_data)
            else:
                st.info("暂无统计数据")
    
    def _get_status_display(self, state: str) -> str:
        """获取状态显示文本"""
        status_map = {
            "detecting": "🔍 检测验证码弹窗",
            "email_stage": "📧 邮箱验证阶段",
            "phone_stage": "📱 电话验证阶段",
            "otp_input": "🔢 等待验证码输入",
            "confirming": "✅ 确认提交中",
            "success": "🎉 处理成功",
            "failed": "❌ 处理失败",
            "user_required": "👤 需要用户操作"
        }
        return status_map.get(state, f"❓ 未知状态: {state}")
    
    def _get_progress_value(self, state: str) -> int:
        """获取进度值"""
        progress_map = {
            "detecting": 10,
            "email_stage": 25,
            "phone_stage": 25,
            "otp_input": 50,
            "confirming": 80,
            "success": 100,
            "failed": 0,
            "user_required": 60
        }
        return progress_map.get(state, 0)
    
    def _get_state_color(self, state: str) -> str:
        """获取状态颜色"""
        color_map = {
            "detecting": "#fff3cd",
            "email_stage": "#d4edda", 
            "phone_stage": "#d4edda",
            "otp_input": "#cce5ff",
            "confirming": "#e2e3e5",
            "success": "#d1ecf1",
            "failed": "#f8d7da",
            "user_required": "#ffeaa7"
        }
        return color_map.get(state, "#ffffff")
    
    def _start_processing(self):
        """开始处理"""
        if self.current_handler:
            self.monitoring_active = True
            
            # 在后台线程中处理验证码
            def process_verification():
                result = self.current_handler.handle_verification()
                self.monitoring_active = False
                
                if result:
                    st.success("🎉 验证码处理成功！")
                else:
                    st.error("❌ 验证码处理失败，请查看详细信息")
            
            # 启动后台处理线程
            processing_thread = threading.Thread(target=process_verification)
            processing_thread.daemon = True
            processing_thread.start()
            
            st.info("⏳ 验证码处理已开始，请关注状态变化...")
    
    def _trigger_continue_processing(self):
        """触发继续处理"""
        # 这里可以实现继续处理的逻辑
        # 例如重新检查状态或发送信号给处理器
        pass
    
    def add_status_record(self, state: str, description: str):
        """添加状态记录"""
        record = {
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'state': self._get_status_display(state),
            'description': description
        }
        self.status_history.append(record)
        
        # 只保留最近50条记录
        if len(self.status_history) > 50:
            self.status_history = self.status_history[-50:]


def create_verification_monitor_app():
    """创建验证码监控应用"""
    st.set_page_config(
        page_title="智能验证码监控",
        page_icon="🔐",
        layout="wide"
    )
    
    # 初始化监控器
    if 'verification_monitor' not in st.session_state:
        st.session_state.verification_monitor = VerificationMonitor()
    
    monitor = st.session_state.verification_monitor
    
    # 模拟验证码处理器（在实际使用中会从外部传入）
    if 'mock_handler' not in st.session_state:
        # 这里应该是真实的验证码处理器实例
        st.session_state.mock_handler = None
    
    # 创建监控界面
    if st.session_state.mock_handler:
        monitor.create_monitoring_interface(st.session_state.mock_handler)
    else:
        st.warning("⚠️ 未检测到活跃的验证码处理器")
        st.info("请先启动验证码处理流程")
        
        # 提供启动选项
        if st.button("🚀 启动模拟验证码处理器"):
            # 这里可以创建一个模拟的处理器用于演示
            st.success("验证码处理器启动成功！")
            st.rerun()


if __name__ == "__main__":
    create_verification_monitor_app() 