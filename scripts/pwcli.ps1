param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$CliArgs
)

$ScriptPath = Join-Path $PSScriptRoot "pwcli_native.py"
& python $ScriptPath @CliArgs
