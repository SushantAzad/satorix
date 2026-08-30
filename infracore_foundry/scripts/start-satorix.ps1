[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Safe','Development','Unrestricted')]
    [string]$Mode,
    [switch]$CheckOnly,
    [switch]$SkipBuild,
    [switch]$AcknowledgeUnrestrictedRisk
)
$ErrorActionPreference = 'Stop'
if ($Mode -eq 'Safe') {
    & (Join-Path $PSScriptRoot 'start-local-safe.ps1') -CheckOnly:$CheckOnly
} elseif ($Mode -eq 'Development') {
    & (Join-Path $PSScriptRoot 'start-development.ps1') -CheckOnly:$CheckOnly
} else {
    & (Join-Path $PSScriptRoot 'start-unrestricted.ps1') -CheckOnly:$CheckOnly -SkipBuild:$SkipBuild -AcknowledgeUnrestrictedRisk:$AcknowledgeUnrestrictedRisk
}
