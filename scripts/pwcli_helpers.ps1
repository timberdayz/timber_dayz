$ErrorActionPreference = "Stop"

function Get-PwcliProjectRoot {
    (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-PwcliScriptPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    Join-Path (Join-Path (Get-PwcliProjectRoot) "scripts") $Name
}

function pwcli {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [object[]]$CliArgs
    )

    & (Get-PwcliScriptPath "pwcli.ps1") @CliArgs
}

Set-Alias pwcli-script (Get-PwcliScriptPath "pwcli.ps1") -Scope Global

function Get-PwcliOutputRoot {
    Join-Path (Get-PwcliProjectRoot) "output\playwright"
}

function Get-PwcliProfileDir {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Platform
    )

    Join-Path (Join-Path (Get-PwcliOutputRoot) "profiles") $Platform.ToLower()
}

function Get-PwcliStateFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Platform
    )

    Join-Path (Join-Path (Get-PwcliOutputRoot) "state") "$($Platform.ToLower()).json"
}

function Get-PwcliWorkDir {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Platform,
        [string]$WorkTag = "explore"
    )

    Join-Path (Join-Path (Join-Path (Get-PwcliOutputRoot) "work") $Platform.ToLower()) $WorkTag
}

function Get-PwcliRuntimeProfileDir {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Platform,
        [Parameter(Mandatory = $true)]
        [string]$AccountId
    )

    $helper = Get-PwcliScriptPath "pwcli_workflow.py"
    python $helper runtime-profile-dir --repo-root (Get-PwcliProjectRoot) --platform $Platform --account-id $AccountId
}

function Get-PwcliDefaultUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Platform
    )

    switch ($Platform.ToLower()) {
        "miaoshou" { "https://erp.91miaoshou.com/welcome" }
        "shopee" { "https://seller.shopee.cn/" }
        "tiktok" { "https://seller.tiktokglobalshop.com/" }
        default { throw "Unknown platform: $Platform" }
    }
}

function Get-PwcliArtifactPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$DefaultExtension
    )

    $ext = [System.IO.Path]::GetExtension($Name)
    if ([string]::IsNullOrWhiteSpace($ext)) {
        return "$Name.$DefaultExtension"
    }
    return $Name
}

function Resolve-PwcliArtifactAbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return (Join-Path (Get-Location).Path $Path)
}

function Get-PwcliActiveSession {
    $session = [string]$env:PLAYWRIGHT_CLI_SESSION
    if ([string]::IsNullOrWhiteSpace($session)) {
        return $null
    }
    return $session.Trim()
}

function Get-PwcliAccountWorkTag {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Platform,
        [Parameter(Mandatory = $true)]
        [string]$AccountId
    )

    # work tag 的规则**只此一份**（Python 侧 scripts/pwcli_account_inventory.py 的 work_tag）。
    # PowerShell 不自己实现一遍：两边各写一遍迟早会不一致，一旦不一致，
    # 同一个账号在「网页面板」和「手工命令」下会落到不同的 session 名与工作目录。
    $helper = Get-PwcliScriptPath "pwcli_account_inventory.py"

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = (python $helper work-tag --platform $Platform --account-id $AccountId 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "Get-PwcliAccountWorkTag failed for platform '$Platform' account '$AccountId' (exit code $exitCode): $output"
    }

    $tag = $output.Trim()
    if (-not $tag) {
        throw "Get-PwcliAccountWorkTag returned an empty work tag for platform '$Platform' account '$AccountId'"
    }
    return $tag
}

function Resolve-PwcliWorkTag {
    param(
        [string]$Platform,
        [string]$WorkTag,
        [string]$AccountId
    )

    if (-not [string]::IsNullOrWhiteSpace($WorkTag)) {
        return $WorkTag.Trim()
    }

    if (-not [string]::IsNullOrWhiteSpace($AccountId)) {
        # 有账号就必须按账号推导：否则多个账号会共用 "explore" 这个**平台级** session 名，
        # 后开的窗口会把先开的窗口杀掉（spec D9 / ③一账号一巡店窗口）。
        return Get-PwcliAccountWorkTag -Platform $Platform -AccountId $AccountId
    }

    return "explore"
}

function Invoke-PwcliSessionCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $pwcliArgs = @()
    $session = Get-PwcliActiveSession
    if ($session) {
        $pwcliArgs += "--session"
        $pwcliArgs += $session
    }
    $pwcliArgs += $Arguments

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = (pwcli @pwcliArgs 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    [pscustomobject]@{
        Output   = $output
        ExitCode = $exitCode
    }
}

function Open-PwcliPlatform {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("miaoshou", "shopee", "tiktok")]
        [string]$Platform,
        [string]$WorkTag = "",
        [string]$Url,
        [string]$AccountId,
        [string]$ProxyServer = "",
        [switch]$NoCd
    )

    $platformName = $Platform.ToLower()
    $resolvedWorkTag = Resolve-PwcliWorkTag -Platform $platformName -WorkTag $WorkTag -AccountId $AccountId
    $workDir = Get-PwcliWorkDir -Platform $platformName -WorkTag $resolvedWorkTag
    $stateFile = Get-PwcliStateFile -Platform $platformName
    $session = "$platformName-$resolvedWorkTag"

    New-Item -ItemType Directory -Force $workDir | Out-Null
    $env:PLAYWRIGHT_CLI_SESSION = $session

    if (-not $NoCd) {
        Set-Location $workDir
    }

    if (-not $Url) {
        $Url = Get-PwcliDefaultUrl -Platform $platformName
    }

    $openArgs = @("--session", $session, "open", $Url, "--headed")
    if ($AccountId) {
        $openArgs += @("--account-id", $AccountId)
    }
    if ($ProxyServer) {
        # 代理地址不含凭据；凭据走 PWCLI_PROXY_USERNAME / PWCLI_PROXY_PASSWORD 环境变量
        $openArgs += @("--proxy-server", $ProxyServer)
    }
    pwcli @openArgs

    if (-not $AccountId -and (Test-Path $stateFile)) {
        $loadOutput = (pwcli --session $session state-load $stateFile 2>&1 | Out-String)
        $loadExitCode = $LASTEXITCODE

        if ($loadExitCode -eq 0) {
            $null = (pwcli --session $session reload 2>&1 | Out-String)
        } else {
            Write-Warning "Failed to load pwcli state from $stateFile. Continuing with a fresh browser state."
        }
    }
}

function Show-PwcliPaths {
    param(
        [ValidateSet("miaoshou", "shopee", "tiktok")]
        [string]$Platform = "miaoshou",
        [string]$AccountId,
        [string]$WorkTag = ""
    )

    $platformName = $Platform.ToLower()
    $resolvedWorkTag = Resolve-PwcliWorkTag -Platform $platformName -WorkTag $WorkTag -AccountId $AccountId
    $runtimeProfileDir = $null
    if ($AccountId) {
        $runtimeProfileDir = (Get-PwcliRuntimeProfileDir -Platform $platformName -AccountId $AccountId | Out-String).Trim()
    }
    [pscustomobject]@{
        ProjectRoot = Get-PwcliProjectRoot
        OutputRoot = Get-PwcliOutputRoot
        ProfileDir = Get-PwcliProfileDir -Platform $platformName
        RuntimeProfileDir = $runtimeProfileDir
        StateFile = Get-PwcliStateFile -Platform $platformName
        WorkDir = Get-PwcliWorkDir -Platform $platformName -WorkTag $resolvedWorkTag
        Session = "$platformName-$resolvedWorkTag"
    }
}

function Open-PwcliMiaoshou {
    param(
        [string]$WorkTag = "",
        [string]$Url = "https://erp.91miaoshou.com/welcome",
        [string]$AccountId,
        [string]$ProxyServer = ""
    )

    Open-PwcliPlatform -Platform miaoshou -WorkTag $WorkTag -Url $Url -AccountId $AccountId -ProxyServer $ProxyServer
}

function Open-PwcliShopee {
    param(
        [string]$WorkTag = "",
        [string]$Url = "https://seller.shopee.cn/",
        [string]$AccountId,
        [string]$ProxyServer = ""
    )

    Open-PwcliPlatform -Platform shopee -WorkTag $WorkTag -Url $Url -AccountId $AccountId -ProxyServer $ProxyServer
}

function Open-PwcliTiktok {
    param(
        [string]$WorkTag = "",
        [string]$Url = "https://seller.tiktokglobalshop.com/",
        [string]$AccountId,
        [string]$ProxyServer = ""
    )

    Open-PwcliPlatform -Platform tiktok -WorkTag $WorkTag -Url $Url -AccountId $AccountId -ProxyServer $ProxyServer
}

function pwsnap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $path = Resolve-PwcliArtifactAbsolutePath (Get-PwcliArtifactPath -Name $Name -DefaultExtension "md")
    $result = Invoke-PwcliSessionCommand -Arguments @("snapshot")
    $content = $result.Output
    $exitCode = $result.ExitCode

    if ($exitCode -ne 0) {
        Write-Error $content
        exit $exitCode
    }

    [System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
    Resolve-Path $path
}

function pwnote {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(ValueFromRemainingArguments = $true)]
        [object[]]$TextParts
    )

    $path = Resolve-PwcliArtifactAbsolutePath (Get-PwcliArtifactPath -Name $Name -DefaultExtension "md")
    $text = ($TextParts -join " ")
    [System.IO.File]::WriteAllText($path, $text + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    Resolve-Path $path
}

function pwshot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$Ref
    )

    $path = Resolve-PwcliArtifactAbsolutePath (Get-PwcliArtifactPath -Name $Name -DefaultExtension "png")
    $before = @{}
    Get-ChildItem -File | Where-Object { $_.Extension -in @(".png", ".jpg", ".jpeg") } | ForEach-Object {
        $before[$_.FullName] = $true
    }

    if ($Ref) {
        $result = Invoke-PwcliSessionCommand -Arguments @("screenshot", $Ref)
    } else {
        $result = Invoke-PwcliSessionCommand -Arguments @("screenshot")
    }
    $output = $result.Output
    $exitCode = $result.ExitCode

    if ($exitCode -ne 0) {
        Write-Error $output
        exit $exitCode
    }

    $created = Get-ChildItem -File |
        Where-Object { $_.Extension -in @(".png", ".jpg", ".jpeg") -and -not $before.ContainsKey($_.FullName) } |
        Sort-Object LastWriteTime -Descending

    if (-not $created) {
        Write-Error "No screenshot artifact was created."
        exit 1
    }

    Move-Item -Force -Path $created[0].FullName -Destination $path
    Resolve-Path $path
}

function pwcap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$Ref
    )

    $session = Get-PwcliActiveSession
    $script = Get-PwcliScriptPath "pw-cap.ps1"
    if ($session) {
        & $script -Name $Name -Ref $Ref -Session $session
    } else {
        & $script -Name $Name -Ref $Ref
    }
}

function pwpack {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("miaoshou", "shopee", "tiktok")]
        [string]$Platform,
        [string]$WorkTag = "explore"
    )

    python (Get-PwcliScriptPath "pwcli_workflow.py") pack --work-dir (Get-PwcliWorkDir -Platform $Platform -WorkTag $WorkTag) --platform $Platform --work-tag $WorkTag
}

function Get-PwcliDailyInspectionAccounts {
    $script = Get-PwcliScriptPath "pwcli_daily_inspection.py"
    $json = python $script "list-accounts" "--format" "json"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to load PWCLI inspection accounts. Check DATABASE_URL and account database availability."
    }
    if ([string]::IsNullOrWhiteSpace($json)) {
        return @()
    }
    $accounts = $json | ConvertFrom-Json
    if ($null -eq $accounts) {
        return @()
    }
    if ($accounts -is [array]) {
        return $accounts
    }
    return @($accounts)
}

function Start-PwcliDailyInspection {
    $accounts = @(Get-PwcliDailyInspectionAccounts)
    if (-not $accounts -or $accounts.Count -eq 0) {
        Write-Output "No enabled PWCLI inspection accounts were found."
        return
    }

    while ($true) {
        Write-Output ""
        Write-Output "PWCLI Daily Inspection Helper"
        Write-Output ""
        for ($i = 0; $i -lt $accounts.Count; $i++) {
            $account = $accounts[$i]
            $number = $i + 1
            Write-Output ("{0}. {1} / {2} [{3}]" -f $number, $account.platform, $account.display_name, $account.account_id)
        }
        Write-Output ""

        $choice = Read-Host "Select account number, or q to quit"
        if ($choice -eq "q") {
            return
        }

        $selectedIndex = 0
        if (-not [int]::TryParse($choice, [ref]$selectedIndex)) {
            Write-Warning "Invalid selection: $choice"
            continue
        }
        if ($selectedIndex -lt 1 -or $selectedIndex -gt $accounts.Count) {
            Write-Warning "Selection out of range: $choice"
            continue
        }

        $account = $accounts[$selectedIndex - 1]
        $proxyServer = [string]$account.proxy_server
        if ($proxyServer) {
            # 代理凭据只走环境变量：命令行在进程列表里可见
            $env:PWCLI_PROXY_USERNAME = [string]$account.proxy_username
            $env:PWCLI_PROXY_PASSWORD = [string]$account.proxy_password
        } else {
            Remove-Item Env:PWCLI_PROXY_USERNAME -ErrorAction SilentlyContinue
            Remove-Item Env:PWCLI_PROXY_PASSWORD -ErrorAction SilentlyContinue
        }

        switch ($account.platform) {
            "miaoshou" {
                Open-PwcliMiaoshou -WorkTag $account.work_tag -AccountId $account.account_id -ProxyServer $proxyServer
            }
            "shopee" {
                Open-PwcliShopee -WorkTag $account.work_tag -AccountId $account.account_id -ProxyServer $proxyServer
            }
            "tiktok" {
                Open-PwcliTiktok -WorkTag $account.work_tag -AccountId $account.account_id -ProxyServer $proxyServer
            }
            default {
                Write-Warning "Unsupported platform: $($account.platform)"
                continue
            }
        }

        Write-Output ""
        Write-Output "Browser opened. Complete manual inspection, close popups, and finish verification in the browser."
        Write-Output "Login state is stored by the browser profile automatically. Close the browser window when you are done."
        $closeChoice = Read-Host "Press Enter after the browser is closed, or q to quit"
        if ($closeChoice -eq "q") {
            return
        }

        # 优雅关闭：CDP Browser.close -> Chromium 刷盘 -> profile 记住登录态
        $activeSession = Get-PwcliActiveSession
        if ($activeSession) {
            $closeResult = Invoke-PwcliSessionCommand -Arguments @("close")
            if ($closeResult.ExitCode -ne 0) {
                Write-Warning "Failed to close browser session '$activeSession': $($closeResult.Output)"
            }
        }
    }
}
