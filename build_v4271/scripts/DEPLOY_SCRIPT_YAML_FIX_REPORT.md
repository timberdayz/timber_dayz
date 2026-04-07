# 部署脚本 YAML 解析错误修复报告

## 问题描述

部署过程中出现 `yaml: line 4: could not find expected ':'` 错误，导致部署失败。

**根本原因**：
- `pull_image_with_fallback()` 函数内部的所有 `echo "[INFO] ..."` 日志输出到 stdout
- 这些日志被命令替换 `$(...)` 捕获，导致 `BACKEND_TAG` 和 `FRONTEND_TAG` 变量包含多行文本
- 多行文本被拼接到 `docker-compose.deploy.yml` 中，导致 YAML 格式错误

## 修复方案

### 1. 修复 `pull_image_with_fallback()` 函数（日志分离）

**修改位置**：`scripts/deploy_remote_production.sh` 第 66-103 行

**修复内容**：
- ✅ 所有日志输出重定向到 stderr（`>&2`）
- ✅ stdout 只输出 tag（单行，无换行符）
- ✅ 确保日志不会影响命令替换的结果

**修改前**：
```bash
echo "[INFO] Attempting to pull ${full_image}..."
echo "${primary_tag}"  # 会被日志行污染
```

**修改后**：
```bash
echo "[INFO] Attempting to pull ${full_image}..." >&2  # stderr
echo "${primary_tag}"  # stdout: only tag
```

### 2. 修复 tag 获取逻辑（清理和验证）

**修改位置**：`scripts/deploy_remote_production.sh` 第 105-128 行

**修复内容**：
- ✅ 直接捕获 stdout（不重定向 stderr，日志正常显示）
- ✅ 清理 tag 值（去除换行符和空格）
- ✅ 添加空值检查

**修改前**：
```bash
BACKEND_TAG="$(pull_image_with_fallback ...)"
# 可能包含多行日志
```

**修改后**：
```bash
BACKEND_TAG="$(pull_image_with_fallback "${IMAGE_NAME_BACKEND}" "${IMAGE_TAG}" | tr -d '\r\n' | xargs)"
if [ -z "${BACKEND_TAG}" ]; then
  echo "[FAIL] Backend tag is empty after pull"
  exit 1
fi
```

### 3. 添加变量验证（防止 YAML 注入）

**修改位置**：`scripts/deploy_remote_production.sh` 第 142-161 行

**修复内容**：
- ✅ 验证必需变量不为空
- ✅ 验证 tag 不包含特殊字符（防止 YAML 注入）
- ✅ 提供清晰的错误消息

**新增代码**：
```bash
# 验证所有必需变量不为空
if [ -z "${GHCR_REGISTRY}" ] || [ -z "${IMAGE_NAME_BACKEND}" ] || [ -z "${IMAGE_NAME_FRONTEND}" ]; then
  echo "[FAIL] Required variables are empty"
  exit 1
fi

# 验证 tag 不包含特殊字符
if echo "${BACKEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]' || echo "${FRONTEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]'; then
  echo "[FAIL] Tag contains invalid characters"
  exit 1
fi
```

### 4. 改进 YAML 生成方式（更安全）

**修改位置**：`scripts/deploy_remote_production.sh` 第 163-171 行

**修复内容**：
- ✅ 使用 `cat` 和 heredoc 替代 `printf`（避免转义问题）
- ✅ 更易读、更安全的 YAML 生成方式

**修改前**：
```bash
printf "services:\n  backend:\n    image: %s/%s:%s\n" \
  "${GHCR_REGISTRY}" "${IMAGE_NAME_BACKEND}" "${BACKEND_TAG}" \
  > docker-compose.deploy.yml
```

**修改后**：
```bash
cat > docker-compose.deploy.yml <<EOF
services:
  backend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_BACKEND}:${BACKEND_TAG}
  frontend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_FRONTEND}:${FRONTEND_TAG}
    ports: []
EOF
```

### 5. 添加 YAML 语法验证（提前发现问题）

**修改位置**：`scripts/deploy_remote_production.sh` 第 175-190 行

**修复内容**：
- ✅ 生成 YAML 后立即验证语法（使用 `docker-compose config`）
- ✅ 验证失败时显示详细错误信息
- ✅ 提前发现问题，避免在部署阶段才报错

**新增代码**：
```bash
if ! "${compose_cmd_base[@]}" config >/dev/null 2>&1; then
  echo "[FAIL] docker-compose config validation failed"
  echo "[INFO] docker-compose.deploy.yml content (first 20 lines):"
  head -20 docker-compose.deploy.yml | nl -ba || true
  echo "[INFO] docker-compose config error output:"
  "${compose_cmd_base[@]}" config 2>&1 | head -30 || true
  exit 1
fi
echo "[OK] docker-compose config validated"
```

## 验证结果

### ✅ 修复验证清单

- [x] `pull_image_with_fallback` 函数所有日志输出到 stderr（`>&2`）
- [x] `pull_image_with_fallback` 函数 stdout 只输出 tag（单行）
- [x] tag 获取逻辑清理换行符和空格
- [x] tag 获取后添加空值检查
- [x] 添加变量非空验证
- [x] 添加 tag 特殊字符验证
- [x] 使用 heredoc 生成 YAML（替代 printf）
- [x] 添加 YAML 语法验证（docker-compose config）
- [x] 脚本语法检查通过（`bash -n`）

### ✅ 防护机制

1. **日志分离**：日志输出到 stderr，不影响命令替换
2. **Tag 清理**：去除换行符、回车符、首尾空格
3. **空值检查**：tag 为空时立即失败
4. **特殊字符验证**：防止 YAML 注入
5. **YAML 语法验证**：提前发现问题

## 预期效果

### 修复前
```
BACKEND_TAG="[INFO] Attempting to pull...
[INFO] Pull attempt 1/3...
[OK] Image pulled successfully...
v4.21.4"
# 多行文本导致 YAML 格式错误
```

### 修复后
```
# 日志显示在终端（stderr）
[INFO] Attempting to pull ghcr.io/backend:v4.21.4...
[INFO] Pull attempt 1/3...
[OK] Image pulled successfully with tag v4.21.4

# tag 变量只包含 tag（stdout）
BACKEND_TAG="v4.21.4"
# 单行文本，YAML 格式正确
```

## 后续验证建议

1. **本地测试**：在本地运行脚本，验证日志和 tag 输出正确
2. **GitHub Actions 验证**：推送新的 tag，观察部署日志：
   - 日志应该正常显示（stderr）
   - tag 变量应该只包含 tag 值（stdout）
   - YAML 验证应该通过
3. **错误场景测试**：
   - 测试 tag 为空的情况
   - 测试 tag 包含特殊字符的情况
   - 测试镜像拉取失败的情况

## 相关文件

- `scripts/deploy_remote_production.sh`：修复后的部署脚本
- `scripts/test_deploy_script_logic.sh`：测试脚本（可选，用于本地验证）

## 修复日期

2025-01-XX
