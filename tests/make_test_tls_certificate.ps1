param([Parameter(Mandatory = $true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$rsa = [System.Security.Cryptography.RSA]::Create(2048)
$request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
    'CN=localhost', $rsa, [System.Security.Cryptography.HashAlgorithmName]::SHA256,
    [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
$san = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
$san.AddDnsName('localhost')
$san.AddIpAddress([System.Net.IPAddress]::Loopback)
$request.CertificateExtensions.Add($san.Build())
$certificate = $request.CreateSelfSigned([DateTimeOffset]::Now.AddDays(-1), [DateTimeOffset]::Now.AddDays(2))
try {
    [System.IO.File]::WriteAllText((Join-Path $OutputDirectory 'cert.pem'), $certificate.ExportCertificatePem())
    [System.IO.File]::WriteAllText((Join-Path $OutputDirectory 'key.pem'), $rsa.ExportPkcs8PrivateKeyPem())
    [System.IO.File]::WriteAllBytes((Join-Path $OutputDirectory 'ca.cer'), $certificate.RawData)
} finally {
    $certificate.Dispose()
    $rsa.Dispose()
}
