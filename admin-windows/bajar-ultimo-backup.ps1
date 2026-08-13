param(
    [string]$Servidor = "root@149.50.150.64",
    [int]$PuertoSsh = 5246
)

$ErrorActionPreference = "Stop"
$destino = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "WC3-Backups"
New-Item -ItemType Directory -Force -Path $destino | Out-Null

$remoto = (& ssh -p $PuertoSsh -o BatchMode=yes $Servidor "ls -1t /opt/wc3/backups/wc3-backup-*.tar.gz 2>/dev/null | head -1").Trim()
if ($LASTEXITCODE -ne 0 -or -not $remoto) {
    throw "No encontre un backup en el VPS."
}

$nombre = Split-Path -Leaf $remoto
$local = Join-Path $destino $nombre
& scp -P $PuertoSsh -o BatchMode=yes "${Servidor}:$remoto" $local
if ($LASTEXITCODE -ne 0) {
    throw "scp no pudo descargar $remoto"
}

& tar -tzf $local | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "El tarball descargado no paso tar -tzf."
}

Write-Host "OK: backup descargado y verificado:" -ForegroundColor Green
Write-Host $local
