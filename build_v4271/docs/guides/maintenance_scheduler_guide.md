# 录制/诊断归档维护 定时任务指南 (Windows)

本指南帮助你在 Windows 上通过计划任务定期执行录制/诊断文件的“非删除式归档”维护。

## 一、脚本位置
- PowerShell 启动脚本：`temp/development/maintenance/run_recording_maintenance.ps1`
- 归档工具：`modules/utils/recording_maintenance.py`
- 报告输出：`temp/logs/maintenance/YYYYMMDD_HHMMSS_recordings_archive_report.txt`

## 二、执行前检查
- 已安装 Python（建议 3.9+），`python --version` 正常
- 仓库路径不包含中文或空格（避免计划任务权限与路径编码问题）
- `config/simple_config.yaml` 中 `collection.maintenance.*` 配置已设置

## 三、手动运行示例
- 预演（DRY-RUN）：
```
powershell -ExecutionPolicy Bypass -File temp/development/maintenance/run_recording_maintenance.ps1 -Platform shopee
```
- 实际归档（APPLY）：
```
powershell -ExecutionPolicy Bypass -File temp/development/maintenance/run_recording_maintenance.ps1 -Platform shopee -Keep 15 -Apply
```

## 四、计划任务配置步骤
1. 打开“任务计划程序”（Task Scheduler）
2. 创建基本任务（Create Basic Task）
3. 触发器（Trigger）：
   - 每周（Weekly），选择合适的日期和时间（建议业务低峰期）
4. 操作（Action）：启动程序（Start a program）
   - Program/script: `powershell`
   - Add arguments: `-ExecutionPolicy Bypass -File "<仓库绝对路径>\temp\development\maintenance\run_recording_maintenance.ps1" -Platform shopee` 
   - Start in: `<仓库绝对路径>`
5. 完成并勾选“使用最高权限运行”（Run with highest privileges），确保移动文件权限

## 五、日志与验证
- 运行日志：终端输出 & 计划任务历史
- 报告文件：`temp/logs/maintenance/.._recordings_archive_report.txt`
- 归档目的地：`backups/YYYYMMDD_recordings_archive/`

## 六、常见问题
- Python 未找到：将 Python 安装路径加入系统 PATH，或修改脚本使用绝对路径
- 权限不足：以管理员身份运行任务计划程序，并启用“使用最高权限运行”
- 占用导致移动失败：确保无进程占用待移动的文件/目录（浏览器或编辑器）

## 七、回滚与安全
- 该工具仅移动文件，绝不删除。若需回滚，可将 `backups/..` 中的对应目录移动回原位置

## 八、进阶
- 平台过滤：`-Platform miaoshou` / `-Platform tiktok`
- 保留数量：`-Keep 20`
- 全量执行：省略 `-Platform`，会对所有平台执行（建议先 DRY-RUN）

> 建议初期以 DRY-RUN 周期性运行，观察报告，再决定切换 -Apply。

