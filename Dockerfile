# ===================================================
# 西虹ERP系统 - 主Dockerfile（兼容性版本）
# ===================================================
# 注意：推荐使用专用Dockerfile：
# - 后端: Dockerfile.backend
# - 前端: Dockerfile.frontend
# 本文件保留用于向后兼容
# ===================================================

# ==================== 基础阶段 ====================
FROM python:3.11-slim as base

LABEL maintainer="西虹ERP团队"
LABEL description="西虹ERP系统 - 混合架构版本"

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p \
    data \
    temp/outputs \
    temp/cache \
    temp/logs \
    logs \
    backups \
    downloads

# ==================== FastAPI后端版本 ====================
FROM base as backend

# 暴露后端端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动FastAPI后端
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ==================== Streamlit前端版本（已废弃） ====================
# 注意：Streamlit前端已移除，项目已迁移到Vue.js 3前端
# 此构建目标保留仅用于向后兼容，但不推荐使用
# FROM base as streamlit
#
# # 暴露Streamlit端口
# EXPOSE 8501
#
# # 健康检查
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD python health_check.py || exit 1
#
# # 启动Streamlit前端
# CMD ["streamlit", "run", "frontend_streamlit/main.py", \
#      "--server.port=8501", \
#      "--server.address=0.0.0.0", \
#      "--server.headless=true"]

# ==================== 默认使用后端版本 ====================
FROM backend

# ===================================================
# 使用说明:
# 
# 构建后端:
#   docker build --target backend -t xihong-erp:backend .
# 
# 构建Streamlit（已废弃，不推荐使用）:
#   docker build --target streamlit -t xihong-erp:streamlit .
# 
# 推荐使用专用Dockerfile:
#   docker build -f Dockerfile.backend -t xihong-erp-backend .
#   docker build -f Dockerfile.frontend -t xihong-erp-frontend .
# ===================================================

