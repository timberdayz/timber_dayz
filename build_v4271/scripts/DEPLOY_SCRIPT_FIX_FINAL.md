# 部署脚本修复最终报告

## 问题总结

### 1. 日志捕获问题
**现象**：`[OK] Resolved tags: Backend=[INFO] Attempting to pull...`  
**原因**：函数内部的日志输出到 stdout，被命令替换 `$(...)` 捕获，导致 tag 变量包含日志内容。

### 2. 镜像拉取慢的问题
**现象**：`docker pull` 步骤耗时近 1 小时  
**原因**：
- 服务器带宽只有 5MB/s
- 国内访问 GHCR 网络延迟高
- 镜像层需要逐层下载

## 修复方案

### 1. 日志捕获修复（已完成）

**修复方法**：使用临时文件方案，分别捕获 stdout 和 stderr

```bash
# 修复前（有问题）
BACKEND_TAG="$(pull_image_with_fallback ... | tr -d '\r\n')"
# 日志会被捕获到 tag 变量中

# 修复后（正确）
TEMP_OUTPUT_FILE=$(mktemp)
TEMP_STDERR_FILE=$(mktemp)
pull_image_with_fallback ... > "${TEMP_OUTPUT_FILE}" 2> "${TEMP_STDERR_FILE}"
cat "${TEMP_STDERR_FILE}" >&2  # 显示日志
BACKEND_TAG="$(grep -v '^\[.*\]' "${TEMP_OUTPUT_FILE}" | tail -n 1 | tr -d '\r\n' | xargs)"
rm -f "${TEMP_OUTPUT_FILE}" "${TEMP_STDERR_FILE}"
```

**关键点**：
- ✅ stdout（tag）和 stderr（日志）分别捕获
- ✅ 日志执行后统一显示（避免实时输出的复杂性）
- ✅ tag 提取时过滤掉可能的日志行（双重保险）
- ✅ 清理临时文件（防止泄露）

### 2. 本地测试脚本（已创建）

**文件**：`scripts/test_deploy_script_locally.sh`

**功能**：
- ✅ 测试 `pull_image_with_fallback` 函数的输出格式（模拟版本）
- ✅ 测试 YAML 生成逻辑
- ✅ 测试 tag 特殊字符验证
- ✅ 测试 docker-compose 语法验证（如果可用）

**使用方法**：
```bash
bash scripts/test_deploy_script_locally.sh
```

**优势**：
- 不依赖实际镜像（不需要拉取镜像）
- 快速验证脚本逻辑（几秒钟完成）
- 可以在本地 CI/CD 中运行（提前发现问题）

### 3. 镜像加速配置（建议）

#### 方案 A：配置 Docker 镜像加速器（推荐）

在服务器上执行：

```bash
# 创建 Docker daemon 配置目录
sudo mkdir -p /etc/docker

# 配置镜像加速器（国内镜像源）
sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com",
    "https://dockerproxy.com"
  ]
}
EOF

# 重启 Docker 服务
sudo systemctl daemon-reload
sudo systemctl restart docker

# 验证配置
docker info | grep -A 5 "Registry Mirrors"
```

**注意**：GHCR（GitHub Container Registry）不在上述镜像加速器的支持列表中，所以这个方案对 GHCR 镜像无效。

#### 方案 B：使用 GHCR 代理（如果可用）

如果服务器有代理，可以配置 Docker 使用代理：

```bash
# 创建 Docker systemd 服务目录
sudo mkdir -p /etc/systemd/system/docker.service.d

# 配置代理
sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf <<EOF
[Service]
Environment="HTTP_PROXY=http://your-proxy:port"
Environment="HTTPS_PROXY=http://your-proxy:port"
Environment="NO_PROXY=localhost,127.0.0.1"
EOF

# 重启 Docker
sudo systemctl daemon-reload
sudo systemctl restart docker
```

#### 方案 C：预先拉取镜像（定时任务）

在服务器上设置定时任务，提前拉取 latest 镜像：

```bash
# 编辑 crontab
crontab -e

# 添加定时任务（每天凌晨 3 点拉取 latest 镜像）
0 3 * * * docker pull ghcr.io/timberdayz/timber_dayz/backend:latest 2>&1 | logger -t docker-pull-backend
0 3 * * * docker pull ghcr.io/timberdayz/timber_dayz/frontend:latest 2>&1 | logger -t docker-pull-frontend
```

**优点**：
- 部署时镜像层可能已缓存，只需拉取差异层
- 减少部署时间

**缺点**：
- 版本标签（如 v4.21.4）仍需从零拉取
- 占用存储空间

#### 方案 D：使用国内镜像仓库中转（复杂，不推荐）

1. 在 GitHub Actions 构建时，同时推送到国内镜像仓库（如阿里云、腾讯云）
2. 部署时从国内镜像仓库拉取

**优点**：
- 拉取速度快（国内网络）

**缺点**：
- 需要维护两套镜像仓库
- 增加 CI/CD 复杂度
- 需要额外的镜像仓库账号和配置

### 4. 再次同步是否还会慢？

**答案**：取决于情况

| 情况 | 拉取速度 | 原因 |
|------|---------|------|
| 镜像层已缓存（相同基础层） | 快（几秒到几分钟） | Docker 使用缓存层，只需拉取新层 |
| 只是 tag 变更（层未变更） | 快（几秒） | 只需更新 tag 引用 |
| 基础层变化（新版本） | 慢（30-60 分钟） | 需要重新下载所有层 |
| 首次部署（服务器无缓存） | 慢（30-60 分钟） | 需要下载所有层 |

**检查镜像层缓存**：
```bash
# 在服务器上执行
docker images | grep "timberdayz/timber_dayz"
docker system df  # 查看 Docker 存储使用情况
```

## 提前发现问题的方案

### 1. 本地测试脚本（已实现）

每次修改部署脚本后，运行：
```bash
bash scripts/test_deploy_script_locally.sh
```

### 2. 添加预检查 GitHub Actions 工作流（可选）

创建 `.github/workflows/pre-deploy-validation.yml`：

```yaml
name: Pre-Deploy Validation

on:
  pull_request:
    paths:
      - 'scripts/deploy_remote_production.sh'
      - 'docker-compose*.yml'
      - '.github/workflows/deploy-production.yml'
  workflow_dispatch:

jobs:
  validate-script:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Validate deploy script syntax
        run: |
          bash -n scripts/deploy_remote_production.sh
          echo "[OK] Script syntax valid"
      
      - name: Test deploy script logic locally
        run: |
          bash scripts/test_deploy_script_locally.sh
          
      - name: Validate docker-compose configs
        run: |
          if command -v docker-compose >/dev/null 2>&1; then
            docker-compose -f docker-compose.yml -f docker-compose.prod.yml config > /dev/null
            if [ -f docker-compose.cloud.yml ]; then
              docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml config > /dev/null
            fi
            echo "[OK] docker-compose configs valid"
          else
            echo "[WARN] docker-compose not found, skipping config validation"
          fi
```

### 3. 部署前检查清单

在推送 tag 前，运行以下检查：

```bash
# 1. 验证脚本语法
bash -n scripts/deploy_remote_production.sh

# 2. 本地测试逻辑
bash scripts/test_deploy_script_locally.sh

# 3. 验证 docker-compose 配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml config > /dev/null

# 4. 检查镜像是否存在（如果知道 tag）
# docker manifest inspect ghcr.io/timberdayz/timber_dayz/backend:v4.21.4
```

## 修复验证

### ✅ 修复验证清单

- [x] 日志捕获问题已修复（使用临时文件方案）
- [x] 本地测试脚本已创建（`scripts/test_deploy_script_locally.sh`）
- [x] YAML 生成逻辑已验证
- [x] tag 提取逻辑已优化（过滤日志行）
- [x] 错误处理已完善（捕获退出码，显示错误日志）
- [x] 临时文件已清理（防止泄露）

### 📋 待办事项（可选）

- [ ] 添加预检查 GitHub Actions 工作流
- [ ] 在服务器上配置 Docker 镜像加速器（对 GHCR 无效，但可以加速其他基础镜像）
- [ ] 设置定时任务预拉取 latest 镜像
- [ ] 考虑使用国内镜像仓库中转（如果需要）

## 修复日期

2025-01-XX
