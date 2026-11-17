# Intentional failures: this helper only accepts an explicitly selected kind context.
param(
  [Parameter(Mandatory=$true)][string]$Context,
  [Parameter(Mandatory=$true)][ValidateSet('crashloop','imagepull','oom','selector')][string]$Scenario,
  [ValidateSet('Apply','Check','Cleanup')][string]$Action = 'Check'
)
$ErrorActionPreference = 'Stop'
if (-not $Context.StartsWith('kind-')) { throw 'This lab helper is restricted to kind contexts.' }
$contexts = @(& kubectl config get-contexts -o name)
if ($LASTEXITCODE -ne 0 -or $contexts -notcontains $Context) { throw 'Context not found.' }
$manifest = Join-Path $PSScriptRoot "../deploy/failures/$Scenario.yaml"
if ($Action -eq 'Apply') {
    # Never adopt an unrelated namespace with the same name.
    $existing = & kubectl --context $Context get namespace ai-agent-lab --ignore-not-found -o json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the lab namespace.' }
    if ($existing) {
        $ns = ($existing -join "`n") | ConvertFrom-Json
        if ($ns.metadata.labels.'app.kubernetes.io/managed-by' -ne 'ai-agent-phase5') { throw 'Namespace exists and is not owned by this lab.' }
    }
    & kubectl --context $Context apply -f (Join-Path $PSScriptRoot '../deploy/failures/namespace.yaml')
    if ($LASTEXITCODE -ne 0) { throw 'Lab namespace setup failed.' }
    & kubectl --context $Context apply -f $manifest
    if ($LASTEXITCODE -ne 0) { throw 'Scenario creation failed.' }
    Write-Host 'Wait for the intended failure, select this context in the dashboard, and investigate.'
} elseif ($Action -eq 'Cleanup') {
    & kubectl --context $Context delete -f $manifest --ignore-not-found
    if ($LASTEXITCODE -ne 0) { throw 'Scenario cleanup failed.' }
} else {
    & kubectl --context $Context get pods,deployments,services -n ai-agent-lab
    & kubectl --context $Context get events -n ai-agent-lab --sort-by=.metadata.creationTimestamp
}
