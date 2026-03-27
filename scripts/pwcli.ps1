param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$CliArgs
)

& npx --yes --package @playwright/cli playwright-cli @CliArgs
