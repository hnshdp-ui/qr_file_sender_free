param(
    [Parameter(Mandatory = $true)]
    [string]$ServerAddress,
    [string]$MkcertPath = ''
)
$ErrorActionPreference = 'Stop'
if (-not $MkcertPath) {
    foreach ($candidate in @("$PSScriptRoot\tools\mkcert.exe", "$PSScriptRoot\mkcert.exe")) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $MkcertPath = $candidate; break }
    }
    if (-not $MkcertPath) {
        $installedMkcert = Get-Command mkcert.exe -CommandType Application -ErrorAction SilentlyContinue
        if ($installedMkcert) { $MkcertPath = $installedMkcert.Source }
    }
}
if (-not $MkcertPath) {
    throw 'mkcert.exe was not found. Put it next to this script or in tools\mkcert.exe, or supply -MkcertPath.'
}
if (-not (Test-Path -LiteralPath $MkcertPath -PathType Leaf)) {
    throw "mkcert executable does not exist: $MkcertPath"
}
# Use a fixed IPv4 address to avoid ambiguities between SANs and browser URLs.
$serverIp = $null
if (-not [System.Net.IPAddress]::TryParse($ServerAddress, [ref]$serverIp) -or
    $serverIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
    [System.Net.IPAddress]::IsLoopback($serverIp) -or $serverIp.Equals([System.Net.IPAddress]::Any)) {
    throw 'ServerAddress must be the Win10 server LAN IPv4 address, such as 192.168.1.50.'
}
$certificateDir = Join-Path $PSScriptRoot 'certs'
New-Item -ItemType Directory -Path $certificateDir -Force | Out-Null
$certFile = Join-Path $certificateDir 'receiver.pem'
$keyFile = Join-Path $certificateDir 'receiver-key.pem'
if ((Test-Path -LiteralPath $certFile) -or (Test-Path -LiteralPath $keyFile)) {
    throw 'Receiver certificates already exist. Rename them before generating replacements; see the deployment guide.'
}
& $MkcertPath -cert-file $certFile -key-file $keyFile $ServerAddress localhost 127.0.0.1
if ($LASTEXITCODE -ne 0) { throw 'mkcert could not generate the receiver certificate.' }
$caRoot = & $MkcertPath -CAROOT
if ($LASTEXITCODE -ne 0) { throw 'mkcert could not locate the CA directory.' }
$publicCa = Join-Path ($caRoot.Trim()) 'rootCA.pem'
$pemText = [System.IO.File]::ReadAllText($publicCa)
$base64 = $pemText.Replace('-----BEGIN CERTIFICATE-----', '').Replace('-----END CERTIFICATE-----', '') -replace '\s', ''
$derFile = Join-Path $certificateDir 'rootCA.cer'
[System.IO.File]::WriteAllBytes($derFile, [Convert]::FromBase64String($base64))
[System.IO.File]::WriteAllText((Join-Path $certificateDir 'server-address.txt'), $ServerAddress)
Write-Host 'HTTPS files are ready. No machine trust settings were changed by this script.'
Write-Host "Start: .\start_receiver_server.cmd --bootstrap-ca"
Write-Host "iPhone CA: http://${ServerAddress}:8000/rootCA.cer"
Write-Host "Receiver: https://${ServerAddress}:8443/"
Write-Host 'Install rootCA.cer on the iPhone and enable full trust for this CA.'
Write-Host 'Keep receiver-key.pem and rootCA-key.pem private; only rootCA.cer is shared.'
Get-FileHash -LiteralPath $derFile -Algorithm SHA256
