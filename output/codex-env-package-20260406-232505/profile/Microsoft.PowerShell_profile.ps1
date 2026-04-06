
# OPENSPEC:START - OpenSpec completion (managed block, do not edit manually)
. "C:\Users\18689\Documents\PowerShell\OpenSpecCompletion.ps1"
# OPENSPEC:END

function pwcli {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [object[]]$CliArgs
    )
    & "F:\Vscode\python_programme\AI_code\xihong_erp\scripts\pwcli.ps1" @CliArgs
}

Set-Alias pwcli-script "F:\Vscode\python_programme\AI_code\xihong_erp\scripts\pwcli.ps1"

function Get-PwcliProjectRoot {
    "F:\Vscode\python_programme\AI_code\xihong_erp"
}

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

    $safePlatformChars = foreach ($ch in $Platform.ToLower().ToCharArray()) {
        if ([char]::IsLetterOrDigit($ch) -or $ch -eq '_' -or $ch -eq '-') {
            $ch
        }
    }
    $safeAccountChars = foreach ($ch in $AccountId.ToCharArray()) {
        if ([char]::IsLetterOrDigit($ch) -or $ch -eq '_' -or $ch -eq '-') {
            $ch
        }
    }

    $safePlatform = -join $safePlatformChars
    $safeAccountId = -join $safeAccountChars

    Join-Path (Join-Path (Get-PwcliProjectRoot) "profiles\$safePlatform") $safeAccountId
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
        [string]$WorkTag = "explore",
        [string]$Url,
        [string]$AccountId,
        [switch]$NoCd
    )

    $platformName = $Platform.ToLower()
    $workDir = Get-PwcliWorkDir -Platform $platformName -WorkTag $WorkTag
    $stateFile = Get-PwcliStateFile -Platform $platformName
    $session = "$platformName-$WorkTag"

    New-Item -ItemType Directory -Force $workDir | Out-Null
    $env:PLAYWRIGHT_CLI_SESSION = $session

    if (-not $NoCd) {
        Set-Location $workDir
    }

    if (-not $Url) {
        $Url = Get-PwcliDefaultUrl -Platform $platformName
    }

    if ($AccountId) {
        pwcli --session $session open $Url --headed --account-id $AccountId
    } else {
        pwcli --session $session open $Url --headed
    }

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

function Save-PwcliPlatformState {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("miaoshou", "shopee", "tiktok")]
        [string]$Platform,
        [string]$AccountId,
        [string]$Filename
    )

    if ($AccountId) {
        $session = Get-PwcliActiveSession
        if ($session) {
            pwcli --session $session state-save
        } else {
            pwcli state-save
        }
        return
    }

    if (-not $Filename) {
        $Filename = Get-PwcliStateFile -Platform $Platform.ToLower()
    }

    New-Item -ItemType Directory -Force (Split-Path -Parent $Filename) | Out-Null
    $session = Get-PwcliActiveSession
    if ($session) {
        pwcli --session $session state-save $Filename
    } else {
        pwcli state-save $Filename
    }
}

function Show-PwcliPaths {
    param(
        [ValidateSet("miaoshou", "shopee", "tiktok")]
        [string]$Platform = "miaoshou",
        [string]$AccountId,
        [string]$WorkTag = "explore"
    )

    $platformName = $Platform.ToLower()
    $runtimeProfileDir = $null
    if ($AccountId) {
        $runtimeProfileDir = (Get-PwcliRuntimeProfileDir -Platform $platformName -AccountId $AccountId | Out-String).Trim()
    }
    [pscustomobject]@{
        ProjectRoot = Get-PwcliProjectRoot
        OutputRoot  = Get-PwcliOutputRoot
        ProfileDir  = Get-PwcliProfileDir -Platform $platformName
        RuntimeProfileDir = $runtimeProfileDir
        StateFile   = Get-PwcliStateFile -Platform $platformName
        WorkDir     = Get-PwcliWorkDir -Platform $platformName -WorkTag $WorkTag
        Session     = "$platformName-$WorkTag"
    }
}

function Open-PwcliMiaoshou {
    param(
        [string]$WorkTag = "explore",
        [string]$Url = "https://erp.91miaoshou.com/welcome",
        [string]$AccountId
    )

    Open-PwcliPlatform -Platform miaoshou -WorkTag $WorkTag -Url $Url -AccountId $AccountId
}

function Open-PwcliShopee {
    param(
        [string]$WorkTag = "explore",
        [string]$Url = "https://seller.shopee.cn/",
        [string]$AccountId
    )

    Open-PwcliPlatform -Platform shopee -WorkTag $WorkTag -Url $Url -AccountId $AccountId
}

function Open-PwcliTiktok {
    param(
        [string]$WorkTag = "explore",
        [string]$Url = "https://seller.tiktokglobalshop.com/",
        [string]$AccountId
    )

    Open-PwcliPlatform -Platform tiktok -WorkTag $WorkTag -Url $Url -AccountId $AccountId
}

function Save-PwcliMiaoshouState {
    param([string]$AccountId)
    Save-PwcliPlatformState -Platform miaoshou -AccountId $AccountId
}

function Save-PwcliShopeeState {
    param([string]$AccountId)
    Save-PwcliPlatformState -Platform shopee -AccountId $AccountId
}

function Save-PwcliTiktokState {
    param([string]$AccountId)
    Save-PwcliPlatformState -Platform tiktok -AccountId $AccountId
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
    if ($session) {
        & "F:\Vscode\python_programme\AI_code\xihong_erp\scripts\pw-cap.ps1" -Name $Name -Ref $Ref -Session $session
    } else {
        & "F:\Vscode\python_programme\AI_code\xihong_erp\scripts\pw-cap.ps1" -Name $Name -Ref $Ref
    }
}

function pwpack {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("miaoshou", "shopee", "tiktok")]
        [string]$Platform,
        [string]$WorkTag = "explore"
    )

    python "F:\Vscode\python_programme\AI_code\xihong_erp\scripts\pwcli_workflow.py" pack --work-dir (Get-PwcliWorkDir -Platform $Platform -WorkTag $WorkTag) --platform $Platform --work-tag $WorkTag
}
