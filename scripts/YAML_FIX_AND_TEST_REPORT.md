# YAML 语法错误修复和测试报告

**日期**: 2026-01-11  
**问题**: `yaml: line 4: could not find expected ':'`  
**修复**: 添加更严格的变量清理、验证和调试信息

---

## 问题分析

### 错误信息

```
yaml: line 4: could not find expected ':'
```

**发生位置**: 生成 `docker-compose.deploy.yml` 后，验证 YAML 语法时

**YAML 第 4 行**:
```yaml
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_BACKEND}:${BACKEND_TAG}
```

### 可能原因

1. **变量中包含不可见字符**（换行符、制表符等）
2. **变量替换时出现问题**（heredoc 变量展开）
3. **验证阶段的错误信息不够详细**（难以诊断）

---

## 修复内容

### 1. 增强变量清理（额外保护）

**位置**: `scripts/deploy_remote_production.sh` 第 183-184 行

**修复**:
```bash
# [FIX] 额外清理：确保 tag 不包含换行符、制表符等控制字符
BACKEND_TAG="$(echo "${BACKEND_TAG}" | tr -d '\r\n\t' | xargs)"
FRONTEND_TAG="$(echo "${FRONTEND_TAG}" | tr -d '\r\n\t' | xargs)"
```

**说明**: 在已有的 tag 提取清理基础上，再次清理控制字符，确保万无一失。

### 2. 添加调试信息（生成前）

**位置**: `scripts/deploy_remote_production.sh` 第 193-199 行

**修复**:
```bash
# [DEBUG] 显示变量值（用于诊断）
echo "[DEBUG] Variables before YAML generation:"
echo "  GHCR_REGISTRY='${GHCR_REGISTRY}'"
echo "  IMAGE_NAME_BACKEND='${IMAGE_NAME_BACKEND}'"
echo "  IMAGE_NAME_FRONTEND='${IMAGE_NAME_FRONTEND}'"
echo "  BACKEND_TAG='${BACKEND_TAG}' (length: ${#BACKEND_TAG})"
echo "  FRONTEND_TAG='${FRONTEND_TAG}' (length: ${#FRONTEND_TAG})"
```

**说明**: 在生成 YAML 前显示所有变量的值，便于诊断问题。

### 3. 添加生成的 YAML 内容显示（生成后）

**位置**: `scripts/deploy_remote_production.sh` 第 213-216 行

**修复**:
```bash
# [DEBUG] 显示生成的 YAML 内容（用于诊断）
echo "[DEBUG] Generated docker-compose.deploy.yml content:"
cat docker-compose.deploy.yml
echo "[DEBUG] End of docker-compose.deploy.yml"
```

**说明**: 生成 YAML 后立即显示内容，确保内容正确。

### 4. 增强验证失败时的错误信息

**位置**: `scripts/deploy_remote_production.sh` 第 232-245 行

**修复**:
```bash
if ! "${compose_cmd_base[@]}" config >/dev/null 2>&1; then
  echo "[FAIL] docker-compose config validation failed"
  echo ""
  echo "[DEBUG] docker-compose.deploy.yml content (with line numbers):"
  cat -n docker-compose.deploy.yml || true
  echo ""
  echo "[DEBUG] docker-compose config error output:"
  "${compose_cmd_base[@]}" config 2>&1 | head -50 || true
  echo ""
  echo "[DEBUG] Variable values at validation time:"
  echo "  BACKEND_TAG='${BACKEND_TAG}' (length: ${#BACKEND_TAG})"
  echo "  FRONTEND_TAG='${FRONTEND_TAG}' (length: ${#FRONTEND_TAG})"
  exit 1
fi
```

**改进**:
- 使用 `cat -n` 显示带行号的 YAML 内容
- 增加错误输出行数（从 30 行增加到 50 行）
- 显示验证时的变量值（包含长度信息）

---

## 测试验证

### 1. 脚本语法验证 ✅

```bash
bash -n scripts/deploy_remote_production.sh
# 结果: 无错误
```

### 2. YAML 生成直接测试 ✅

**测试脚本**: `scripts/test_yaml_generation_direct.sh`

**测试内容**:
- 使用实际变量值生成 YAML
- 验证 YAML 基本结构
- 验证第 4 行包含 `:` 字符
- 验证 `image:` 键存在

**测试结果**:
```
[OK] YAML structure validation passed
[OK] Line 4 contains ':' as expected
[OK] All YAML generation tests passed!
```

### 3. 边界情况测试 ✅

**测试脚本**: `scripts/test_yaml_generation_edge_cases.sh`

**测试用例**:
- ✅ 正常 tag（`v4.21.4`）
- ✅ 不带 `v` 前缀的 tag（`4.21.4`）
- ✅ 带连字符的 tag（`v4.21.4-beta`）
- ✅ 带下划线的 tag（如果支持）

**测试结果**:
```
[OK] All edge case tests passed!
```

---

## 修复效果

### 修复前

- ❌ 变量清理可能不完整
- ❌ 缺少调试信息，难以诊断问题
- ❌ 验证失败时错误信息不够详细

### 修复后

- ✅ 双重清理：tag 提取时清理 + 生成前再次清理
- ✅ 生成前后都显示调试信息
- ✅ 验证失败时显示完整的 YAML 内容和变量值
- ✅ 所有测试通过

---

## 防护机制

1. **Tag 提取清理**: `grep -v '^\[.*\]' | tail -n 1 | tr -d '\r\n' | xargs`
2. **生成前清理**: `echo "${TAG}" | tr -d '\r\n\t' | xargs`
3. **特殊字符验证**: `grep -qE '[^a-zA-Z0-9._-]'`
4. **空值检查**: `[ -z "${TAG}" ]`
5. **YAML 语法验证**: `docker-compose config`
6. **详细错误输出**: 显示 YAML 内容、行号、变量值

---

## 相关文件

- `scripts/deploy_remote_production.sh`: 修复后的部署脚本
- `scripts/test_yaml_generation_direct.sh`: 直接 YAML 生成测试
- `scripts/test_yaml_generation_edge_cases.sh`: 边界情况测试

---

## 总结

✅ **修复完成**: 添加了更严格的变量清理和详细的调试信息  
✅ **测试通过**: 所有测试用例通过  
✅ **错误诊断**: 验证失败时提供完整的调试信息  

**下一步**:
1. 提交修复后的代码
2. 创建新的 tag（如 `v4.22.1`）触发自动部署
3. 观察部署日志中的调试信息，确认 YAML 生成正确
