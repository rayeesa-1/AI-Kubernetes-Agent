param([Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9][a-z0-9-]*$')][string]$ClusterName)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$context = "kind-$ClusterName"
# Administrative setup only. The application receives a read-only identity.
& kubectl --context $context apply -f deploy/investigator-rbac.yaml
if ($LASTEXITCODE -ne 0) { throw 'RBAC setup failed. Check the cluster name and admin context.' }
$internalConfig = & kind get kubeconfig --name $ClusterName --internal
if ($LASTEXITCODE -ne 0) { throw 'Could not obtain kind internal connection settings.' }
# Read only this admin context into memory; replace it with a short-lived identity below.
$configText = & kubectl --context $context config view --raw --flatten --minify -o json
if ($LASTEXITCODE -ne 0) { throw 'Could not convert kubeconfig.' }
$config = ($configText -join "`n") | ConvertFrom-Json
$serverLine = $internalConfig | Where-Object { $_ -match '^\s*server:\s*(https://\S+)\s*$' } | Select-Object -First 1
if (-not $serverLine) { throw 'Could not find internal kind API server address.' }
$internalServer = ($serverLine -replace '^\s*server:\s*', '').Trim()
$config.clusters[0].cluster.server = $internalServer
$token = & kubectl --context $context -n ai-investigator create token evidence-reader --duration=8h
if ($LASTEXITCODE -ne 0) { throw 'Could not issue read-only token.' }
$config.users = @(@{ name='evidence-reader'; user=@{ token=($token -join '').Trim() } })
foreach ($entry in $config.contexts) { $entry.context.user = 'evidence-reader' }
New-Item -ItemType Directory -Force .kube | Out-Null
$destination = Join-Path (Get-Location) '.kube/kind-config.json'
[IO.File]::WriteAllText($destination, ($config | ConvertTo-Json -Depth 30), [Text.UTF8Encoding]::new($false))
# Use the cluster's own version for the container's kubectl binary.
$versionText = & kubectl --context $context version -o json
if ($LASTEXITCODE -ne 0) { throw 'Could not obtain server version.' }
$version = (($versionText -join "`n") | ConvertFrom-Json).serverVersion.gitVersion
Write-Host "Read-only configuration written. Token requested for 8h; rerun this script when it expires."
Write-Host "Run: `$env:KUBECTL_VERSION='$version'"
Write-Host 'Then follow docs/phase-2-windows.md to build and test.'
