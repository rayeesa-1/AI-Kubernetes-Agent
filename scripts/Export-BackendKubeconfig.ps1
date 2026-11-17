# Run with Windows PowerShell from the project root. Requires kubectl and kind.
# Exports credentials locally; never commit, upload, or print the output file.
param([string]$OutputPath = 'kind-backend.kubeconfig')
$ErrorActionPreference = 'Stop'
Get-Command kubectl -ErrorAction Stop | Out-Null
$rawConfig = & kubectl config view --raw --flatten -o json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read Windows kubeconfig.' }
try { $config = ($rawConfig -join "`n") | ConvertFrom-Json } catch { throw 'Cannot parse kubeconfig. No file was written.' }
if (-not $config.contexts) { throw 'No kubeconfig contexts found.' }
# Docker's kind network can resolve the internal control-plane container names.
# Preserve non-kind entries as exported; their network/plugin setup may need work.
if (Get-Command kind -ErrorAction SilentlyContinue) {
    $kindNames = @(& kind get clusters)
    if ($LASTEXITCODE -ne 0) { throw 'Could not list kind clusters.' }
    foreach ($kindName in $kindNames) {
        if (-not $kindName.Trim()) { continue }
        $context = @($config.contexts | Where-Object { $_.name -eq "kind-$kindName" })
        if (-not $context.Count) { continue }
        $internalRaw = & kind get kubeconfig --name $kindName --internal
        if ($LASTEXITCODE -ne 0) { throw 'Could not export an internal kind configuration.' }
        # Convert the YAML through kubectl, using a private temporary file.
        $tempFile = [IO.Path]::GetTempFileName()
        try {
            [IO.File]::WriteAllText($tempFile, ($internalRaw -join "`n"), (New-Object Text.UTF8Encoding($false)))
            $internalJson = & kubectl --kubeconfig $tempFile config view --raw -o json
            if ($LASTEXITCODE -ne 0) { throw 'Could not parse internal kind configuration.' }
            try { $internal = ($internalJson -join "`n") | ConvertFrom-Json } catch { throw 'Invalid kind configuration.' }
            foreach ($entry in $config.clusters) {
                if ($entry.name -eq $context[0].context.cluster) { $entry.cluster = $internal.clusters[0].cluster }
            }
        } finally { Remove-Item $tempFile -Force -ErrorAction SilentlyContinue }
    }
}
$fullPath = [IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
[IO.File]::WriteAllText($fullPath, ($config | ConvertTo-Json -Depth 100), (New-Object Text.UTF8Encoding($false)))
Write-Host 'Backend kubeconfig exported. Keep it private and restart the backend to remount it.'
Write-Host 'Non-kind local endpoints, file paths, credential plugins, and remote firewalls may need separate container configuration.'
