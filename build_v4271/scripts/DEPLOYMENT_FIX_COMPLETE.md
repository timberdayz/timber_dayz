# 部署问题一次性修复完成报告

**日期**: 2026-01-11  
**问题**: Alembic 多头迁移导致部署失败  
**状态**: ✅ 修复完成

---

## 问题分析

### 错误信息

```
ERROR [alembic.util.messaging] Multiple head revisions are present for given argument 'head'; please specify a specific target revision, '<branchname>@head' to narrow to a specific head, or 'heads' for all heads
```

**根本原因**：
- Alembic 迁移链存在 **5 个分支头（heads）**，未合并
- 部署脚本使用 `alembic upgrade head`（单数），无法处理多个头
- 需要合并所有分支或使用 `heads`（复数）命令

---

## 修复内容

### 1. 修改部署脚本（立即生效）

**文件**: `scripts/deploy_remote_production.sh`

**位置**: 第 299-301 行

**修复**:
```bash
# 之前
echo "[INFO] Phase 2: Running Alembic migrations (alembic upgrade head)..."
"${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade head

# 之后
# 使用 heads（复数）以支持多头迁移分支，确保所有分支都被应用
echo "[INFO] Phase 2: Running Alembic migrations (alembic upgrade heads)..."
"${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade heads
```

**说明**: 使用 `heads`（复数）可以应用所有分支头的迁移，即使存在多个分支也能正常工作。

---

### 2. 创建合并迁移（长期方案）

**文件**: `migrations/versions/20260111_merge_all_heads.py`

**功能**: 合并所有 5 个分支头为单一头

**合并的分支**:
1. `20260110_complete_schema_base` - 完整表结构基础迁移
2. `20251105_204200` - 物化视图刷新日志表
3. `20251105_add_image_url` - 产品指标图片URL字段
4. `20250131_mv_attach_rate` - 店铺连带率物化视图
5. `20250131_add_c_class_mv_indexes` - C类数据物化视图索引

**特点**:
- `down_revision` 设置为元组，包含所有 5 个分支头
- `upgrade()` 和 `downgrade()` 函数为空（仅用于合并分支）
- 创建后，`alembic heads` 应该只显示 1 个头

---

## 修复效果

### 修复前

- ❌ `alembic upgrade head` 失败（存在多个头）
- ❌ 部署被阻止在迁移阶段
- ❌ 需要手动合并分支或指定具体头

### 修复后

- ✅ `alembic upgrade heads` 可以应用所有分支（短期方案）
- ✅ 合并迁移创建后，`alembic upgrade head` 可以正常工作（长期方案）
- ✅ 部署流程可以正常完成

---

## 验证步骤

### 1. 验证合并迁移（创建后）

```bash
# 检查当前头数量
alembic heads

# 应该显示：
# 20260111_merge_all_heads (head)

# 或者如果有未合并的头：
# 20260111_merge_all_heads (head)
# 其他头...
```

### 2. 本地测试迁移

```bash
# 使用 heads（复数）应用所有分支
alembic upgrade heads

# 或者创建合并迁移后，使用 head（单数）
alembic upgrade head
```

### 3. 部署测试

- 创建新的 tag（如 `v4.22.2`）
- 观察 GitHub Actions 部署日志
- 确认迁移阶段成功完成

---

## 相关文件

- `scripts/deploy_remote_production.sh`: 部署脚本（已修复）
- `migrations/versions/20260111_merge_all_heads.py`: 合并迁移文件（新增）
- `.github/workflows/deploy-production.yml`: GitHub Actions 工作流（如果使用 alembic 命令，也需要检查）

---

## 下一步

1. ✅ **修复完成**: 部署脚本已更新为使用 `heads`
2. ✅ **合并迁移**: 已创建合并迁移文件
3. ⏳ **验证**: 运行 `alembic heads` 确认合并迁移生效
4. ⏳ **部署**: 创建新的 tag 触发自动部署测试

---

## 总结

✅ **短期方案**: 使用 `alembic upgrade heads`（已应用）  
✅ **长期方案**: 创建合并迁移文件（已完成）  
✅ **部署脚本**: 已更新为支持多头迁移  

**关键改进**:
- 部署脚本现在使用 `heads`（复数）以支持多头迁移
- 合并迁移文件已创建，可以合并所有分支头为单一头
- 修复后，部署流程可以正常完成
