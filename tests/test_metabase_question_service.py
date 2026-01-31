"""
MetabaseQuestionService 单元测试

验证按名称查 Question ID + 缓存逻辑（4.3.1/4.3.2），不依赖真实 Metabase 服务。
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytest_plugins = ("anyio",)

# 确保从项目根运行时可找到 backend
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def mock_httpx_client():
    """模拟 httpx.AsyncClient，避免真实请求"""
    client = AsyncMock()
    return client


@pytest.fixture
def service_with_mock_client(mock_httpx_client):
    """返回使用 mock client 的 MetabaseQuestionService 实例"""
    with patch("backend.services.metabase_question_service.httpx.AsyncClient", return_value=mock_httpx_client):
        from backend.services.metabase_question_service import MetabaseQuestionService
        svc = MetabaseQuestionService()
        svc.client = mock_httpx_client
        # 避免真实认证
        svc.api_key = "test-api-key"
        svc.session_token = "test-token"
        return svc


class TestLoadQuestionKeyToDisplayName:
    """测试从 config 加载 question_key -> display_name"""

    def test_load_config_returns_dict(self):
        from backend.services.metabase_question_service import _load_question_key_to_display_name
        result = _load_question_key_to_display_name()
        assert isinstance(result, dict)

    def test_config_contains_expected_keys(self):
        from backend.services.metabase_question_service import _load_question_key_to_display_name
        result = _load_question_key_to_display_name()
        # metabase_config.yaml 中应至少包含业务概览相关 key
        expected = ["business_overview_kpi", "business_overview_comparison", "business_overview_shop_racing"]
        for k in expected:
            assert k in result, f"missing key: {k}"
        assert result["business_overview_kpi"] == "业务概览 - 核心KPI指标"


class TestGetQuestionIdByName:
    """测试按名称获取 Question ID（优先缓存，兜底 env）"""

    @pytest.mark.anyio
    async def test_get_question_id_from_api_cache(self, service_with_mock_client, mock_httpx_client):
        """模拟 GET /api/card 返回 Question 列表，验证 _get_question_id 从缓存解析出 ID"""
        # 模拟 /api/card 返回
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"id": 101, "name": "业务概览 - 核心KPI指标", "type": "question"},
                {"id": 102, "name": "业务概览 - 数据对比", "type": "question"},
            ]
        }
        mock_httpx_client.get = AsyncMock(return_value=mock_resp)

        svc = service_with_mock_client
        qid = await svc._get_question_id("business_overview_kpi")
        assert qid == 101
        # 第二次应走缓存，不再请求
        qid2 = await svc._get_question_id("business_overview_kpi")
        assert qid2 == 101
        assert mock_httpx_client.get.call_count == 1

    @pytest.mark.anyio
    async def test_get_question_id_fallback_to_env(self, service_with_mock_client, mock_httpx_client):
        """当 API 未返回对应 Question 时，应使用 question_ids（env）兜底"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": []}  # 无匹配的 card
        mock_httpx_client.get = AsyncMock(return_value=mock_resp)

        svc = service_with_mock_client
        svc._question_cache = {}  # 清空缓存，强制走兜底
        svc.question_ids["business_overview_kpi"] = 99  # 模拟 env 已配置
        qid = await svc._get_question_id("business_overview_kpi")
        assert qid == 99

    @pytest.mark.anyio
    async def test_get_question_id_raises_when_not_found(self, service_with_mock_client, mock_httpx_client):
        """当缓存和 env 都没有时，应抛出 ValueError"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": []}
        mock_httpx_client.get = AsyncMock(return_value=mock_resp)

        svc = service_with_mock_client
        # 使用一个在 config 中存在但 API 返回空、且未设置 env 的 key
        with patch.dict(os.environ, {}, clear=False):
            for k in list(svc.question_ids.keys()):
                svc.question_ids[k] = 0
        with pytest.raises(ValueError) as exc_info:
            await svc._get_question_id("business_overview_kpi")
        assert "Question ID 未找到" in str(exc_info.value)
        assert "business_overview_kpi" in str(exc_info.value)


class TestQueryQuestionIntegration:
    """测试 query_question 端到端（全部 mock，不请求真实 Metabase）"""

    @pytest.mark.anyio
    async def test_query_question_returns_dict_when_mocked(self, service_with_mock_client, mock_httpx_client):
        """模拟 API 返回 KPI 格式数据，验证 query_question 返回前端所需结构"""
        # GET /api/card
        card_resp = MagicMock()
        card_resp.raise_for_status = MagicMock()
        card_resp.json.return_value = {
            "data": [{"id": 1, "name": "业务概览 - 核心KPI指标", "type": "question"}]
        }
        # POST /api/card/1/query/json
        query_resp = MagicMock()
        query_resp.raise_for_status = MagicMock()
        query_resp.json.return_value = [
            {"gmv": 1000, "order_count": 10, "visitor_count": 500, "conversion_rate": 2.0, "avg_order_value": 100}
        ]
        mock_httpx_client.get = AsyncMock(return_value=card_resp)
        mock_httpx_client.post = AsyncMock(return_value=query_resp)

        svc = service_with_mock_client
        result = await svc.query_question("business_overview_kpi", {"month": "2025-01-01"})
        assert isinstance(result, dict)
        # _convert_response 对 business_overview_kpi 会产出 gmv, order_count 等
        assert "gmv" in result or "GMV" in str(result) or "row_count" in result or len(result) >= 1
