"""
可靠性服务单元测试

测试清理服务、任务服务、WebSocket等可靠性组件
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

# 配置pytest-anyio
pytestmark = pytest.mark.anyio


# ============================================================
# CleanupService 测试
# ============================================================

class TestCleanupService:
    """清理服务测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def cleanup_service(self, temp_dir):
        """创建清理服务实例"""
        from backend.services.cleanup_service import CleanupService
        return CleanupService(temp_dir=str(temp_dir))
    
    def test_init(self, cleanup_service, temp_dir):
        """测试初始化"""
        assert cleanup_service.temp_dir == temp_dir
        assert cleanup_service.downloads_dir == temp_dir / 'downloads'
        assert cleanup_service.screenshots_dir == temp_dir / 'screenshots'
    
    def test_cleanup_downloads_empty(self, cleanup_service, temp_dir):
        """测试清理空下载目录"""
        result = cleanup_service.cleanup_downloads()
        
        assert result['type'] == 'downloads'
        assert result['files_deleted'] == 0
        assert result['dirs_deleted'] == 0
    
    def test_cleanup_downloads_with_old_files(self, cleanup_service, temp_dir):
        """测试清理过期下载文件"""
        downloads_dir = temp_dir / 'downloads'
        downloads_dir.mkdir()
        
        # 创建过期目录
        old_task_dir = downloads_dir / 'old-task-123'
        old_task_dir.mkdir()
        (old_task_dir / 'file1.xlsx').write_text('test')
        (old_task_dir / 'file2.xlsx').write_text('test')
        
        # 修改时间为10天前
        old_time = (datetime.now() - timedelta(days=10)).timestamp()
        os.utime(old_task_dir, (old_time, old_time))
        
        # 创建新目录
        new_task_dir = downloads_dir / 'new-task-456'
        new_task_dir.mkdir()
        (new_task_dir / 'file3.xlsx').write_text('test')
        
        # 执行清理
        result = cleanup_service.cleanup_downloads(retention_days=7)
        
        assert result['dirs_deleted'] == 1
        assert result['files_deleted'] == 2
        assert not old_task_dir.exists()
        assert new_task_dir.exists()
    
    def test_cleanup_screenshots_empty(self, cleanup_service, temp_dir):
        """测试清理空截图目录"""
        result = cleanup_service.cleanup_screenshots()
        
        assert result['type'] == 'screenshots'
        assert result['files_deleted'] == 0
    
    def test_get_temp_stats(self, cleanup_service, temp_dir):
        """测试获取临时文件统计"""
        downloads_dir = temp_dir / 'downloads'
        downloads_dir.mkdir()
        
        task_dir = downloads_dir / 'task-123'
        task_dir.mkdir()
        (task_dir / 'file.xlsx').write_text('x' * 100)
        
        stats = cleanup_service.get_temp_stats()
        
        assert stats['downloads']['count'] == 1
        assert stats['downloads']['size_bytes'] == 100
    
    def test_run_full_cleanup(self, cleanup_service, temp_dir):
        """测试完整清理"""
        result = cleanup_service.run_full_cleanup()
        
        assert 'timestamp' in result
        assert 'downloads' in result
        assert 'screenshots' in result
        assert 'orphan_browsers' in result
        assert 'summary' in result


# ============================================================
# TaskService 测试
# ============================================================

class TestTaskService:
    """任务服务测试"""
    
    @pytest.fixture
    def mock_db(self):
        """创建模拟数据库会话"""
        db = Mock()
        db.query.return_value.filter.return_value.count.return_value = 0
        db.execute.return_value.rowcount = 1
        return db
    
    @pytest.fixture
    def task_service(self, mock_db):
        """创建任务服务实例"""
        from backend.services.task_service import TaskService
        return TaskService(mock_db)
    
    def test_init(self, task_service, mock_db):
        """测试初始化"""
        assert task_service.db == mock_db
    
    def test_get_running_count(self, task_service, mock_db):
        """测试获取运行中任务数"""
        mock_db.query.return_value.filter.return_value.count.return_value = 5
        
        count = task_service.get_running_count()
        
        assert count == 5
    
    def test_can_start_new_task_yes(self, task_service, mock_db):
        """测试可以启动新任务"""
        mock_db.query.return_value.filter.return_value.count.return_value = 1
        
        can_start = task_service.can_start_new_task()
        
        assert can_start is True
    
    def test_can_start_new_task_no(self, task_service, mock_db):
        """测试不能启动新任务（达到并发限制）"""
        mock_db.query.return_value.filter.return_value.count.return_value = 10
        
        can_start = task_service.can_start_new_task()
        
        assert can_start is False
    
    def test_check_account_conflict_no(self, task_service, mock_db):
        """测试没有账号冲突"""
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        
        has_conflict = task_service.check_account_conflict('account1', 'shopee')
        
        assert has_conflict is False
    
    def test_check_account_conflict_yes(self, task_service, mock_db):
        """测试有账号冲突"""
        mock_db.query.return_value.filter.return_value.count.return_value = 1
        
        has_conflict = task_service.check_account_conflict('account1', 'shopee')
        
        assert has_conflict is True
    
    def test_validate_status_transition_valid(self, task_service):
        """测试有效的状态转换"""
        assert task_service.validate_status_transition('pending', 'running') is True
        assert task_service.validate_status_transition('running', 'completed') is True
        assert task_service.validate_status_transition('running', 'paused') is True
    
    def test_validate_status_transition_invalid(self, task_service):
        """测试无效的状态转换"""
        assert task_service.validate_status_transition('completed', 'running') is False
        assert task_service.validate_status_transition('failed', 'completed') is False


# ============================================================
# WebSocket 测试
# ============================================================

class TestConnectionManager:
    """WebSocket连接管理器测试"""
    
    @pytest.fixture
    def manager(self):
        """创建连接管理器"""
        from backend.routers.collection_websocket import ConnectionManager
        return ConnectionManager()
    
    async def test_connect(self, manager):
        """测试连接"""
        mock_ws = AsyncMock()
        
        result = await manager.connect(mock_ws, 'task-123')
        
        assert result is True
        assert 'task-123' in manager.active_connections
        assert mock_ws in manager.active_connections['task-123']
    
    async def test_disconnect(self, manager):
        """测试断开连接"""
        mock_ws = AsyncMock()
        await manager.connect(mock_ws, 'task-123')
        
        manager.disconnect(mock_ws, 'task-123')
        
        assert 'task-123' not in manager.active_connections
    
    async def test_broadcast_to_task(self, manager):
        """测试广播消息"""
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        
        await manager.connect(mock_ws1, 'task-123')
        await manager.connect(mock_ws2, 'task-123')
        
        message = {'type': 'progress', 'progress': 50}
        await manager.broadcast_to_task('task-123', message)
        
        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)
    
    async def test_send_progress(self, manager):
        """测试发送进度更新"""
        mock_ws = AsyncMock()
        await manager.connect(mock_ws, 'task-123')
        
        await manager.send_progress('task-123', 50, 'Processing...', 'running')
        
        mock_ws.send_json.assert_called_once()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args['type'] == 'progress'
        assert call_args['progress'] == 50
    
    async def test_send_complete(self, manager):
        """测试发送完成通知"""
        mock_ws = AsyncMock()
        await manager.connect(mock_ws, 'task-123')
        
        await manager.send_complete('task-123', 'completed', files_collected=5)
        
        mock_ws.send_json.assert_called_once()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args['type'] == 'complete'
        assert call_args['status'] == 'completed'
        assert call_args['files_collected'] == 5
    
    def test_get_connection_count(self, manager):
        """测试获取连接数"""
        assert manager.get_connection_count() == 0
    
    def test_get_active_task_ids(self, manager):
        """测试获取活跃任务ID"""
        assert manager.get_active_task_ids() == []


class TestJWTValidation:
    """JWT验证测试"""
    
    def test_validate_valid_token(self):
        """测试验证有效Token"""
        import jwt
        from backend.routers.collection_websocket import validate_jwt_token, JWT_SECRET, JWT_ALGORITHM
        
        # 创建有效token
        payload = {'user_id': 'test', 'exp': datetime.utcnow() + timedelta(hours=1)}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        result = validate_jwt_token(token)
        
        assert result['user_id'] == 'test'
    
    def test_validate_invalid_token(self):
        """测试验证无效Token"""
        from backend.routers.collection_websocket import validate_jwt_token
        
        with pytest.raises(ValueError, match="Invalid token"):
            validate_jwt_token("invalid-token")
    
    def test_validate_expired_token(self):
        """测试验证过期Token"""
        import jwt
        from backend.routers.collection_websocket import validate_jwt_token, JWT_SECRET, JWT_ALGORITHM
        
        # 创建过期token
        payload = {'user_id': 'test', 'exp': datetime.utcnow() - timedelta(hours=1)}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        with pytest.raises(ValueError, match="expired"):
            validate_jwt_token(token)
    
    def test_validate_empty_token(self):
        """测试验证空Token"""
        from backend.routers.collection_websocket import validate_jwt_token
        
        with pytest.raises(ValueError, match="required"):
            validate_jwt_token("")

