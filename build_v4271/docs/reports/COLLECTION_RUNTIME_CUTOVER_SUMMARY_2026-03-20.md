# 采集正式运行主路径收敛变更摘要

日期：2026-03-20

## 目标

将采集系统的正式运行路径收敛为唯一主路径：

`stable ComponentVersion -> file_path -> executor`

并切断以下旧路径进入正式采集的能力：

- 原始录制脚本
- `temp/recordings/` 中间产物
- 旧模板生成器直接生成的脚本
- 正式运行路径中的模块名兜底加载

## 已完成变更

### 1. 正式运行解析器

- 新增 `backend/services/component_runtime_resolver.py`
- 正式任务创建和调度任务触发都会先解析 stable 版本
- 没有 stable、多个 stable、stable 文件缺失时会 fail fast

### 2. 执行器正式路径

- `CollectionExecutorV2` 已支持消费 `runtime_manifests`
- 正式运行按 manifest 中的 `file_path` 加载组件
- 顺序执行与并行执行都已接入 stable manifest
- adapter 保留给测试/调试路径，不再作为正式任务最终组件选择器

### 3. 版本管理语义

- 新注册组件版本默认为草稿（draft-first）
- 正式运行只允许 stable 版本
- `promote_to_stable` 的唯一稳定版语义已补测试

### 4. 录制与文档

- 录制保存成功提示已明确为“草稿版本”
- 版本管理页已明确“只有稳定版本可用于正式采集和定时调度”
- 旧模板生成器已标记为历史/调试用途
- 脚本规范文档已加入 stable-only 正式运行约束

### 5. 回归与测试清理

- 为 runtime resolver、component version service、executor runtime path 补充了回归测试
- 清理了 `pytest` 默认收集中的历史脚本干扰
- 更新了一批与当前实现不一致的旧测试预期

## 验证结果

执行：

```bash
pytest
```

结果：

- 通过：`512 passed`
- 跳过：`8 skipped`

## 仍然保留的边界

- 本次未拆分浏览器采集 worker 出 API 进程
- 仍存在若干第三方/历史兼容 warning，但不影响测试通过
- 用户当前工作区里仍有未提交的本地改动，与本次主路径收敛逻辑无直接冲突

## 结论

这次收敛完成后，采集系统的正式运行、录制保存、版本晋升、执行器加载四者的边界已经清晰：

- 录制产物不是正式运行资产
- 保存不等于发布
- stable 才是正式运行资格
- executor 只认 stable file_path
