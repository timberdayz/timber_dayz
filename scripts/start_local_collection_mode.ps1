$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$env:XIHONG_ENV_PROFILE = "development"

Write-Host "[Mode] Local development: local backend and frontend, Docker infrastructure only"
Write-Host "[Guard] Docker backend/celery containers will be stopped before startup"

# 逐个停：一个容器不存在不能让其余的停不下来（docker stop 多容器时整条会失败）。
# celery worker/beat 也在写同一个库，刷新物化视图时长期持锁，
# 会把迁移前的 pg_dump 备份堵死 ⇒ 备份校验失败 ⇒ 启动被 fail-closed 拦停。
#
# 不写成 `docker stop $c 2>&1 | Out-Null`：原生 stderr 进了 2>&1 会被 PowerShell
# 转成 ErrorRecord，在 $ErrorActionPreference="Stop" 下直接打断脚本 ——
# 容器不存在时 docker 恰恰就往 stderr 写 "No such container"。
$conflictContainers = @(
    "xihong_erp_backend_api",
    "xihong_erp_backend_collector",
    "xihong_erp_celery_worker",
    "xihong_erp_celery_beat"
)
$previousStopErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    foreach ($conflictContainer in $conflictContainers) {
        docker stop $conflictContainer | Out-Null
        $stopExitCode = $LASTEXITCODE
        if ($stopExitCode -eq 0) {
            Write-Host "[Guard] stopped $conflictContainer"
        } else {
            Write-Host "[INFO] skip docker stop $conflictContainer (not running or missing)"
        }
    }
} finally {
    $ErrorActionPreference = $previousStopErrorActionPreference
}

& python "$repoRoot\run.py" --local
exit $LASTEXITCODE
