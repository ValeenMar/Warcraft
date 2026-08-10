$ErrorActionPreference = 'Stop'

$Servidor = 'root@64.176.24.103'
$PuertoLocal = 18322
$PuertoRemoto = 8322
$Url = "http://127.0.0.1:$PuertoLocal/"
$Ssh = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'

function Test-PuertoLocal {
    $cliente = [Net.Sockets.TcpClient]::new()
    try {
        $tarea = $cliente.ConnectAsync('127.0.0.1', $PuertoLocal)
        return $tarea.Wait(600) -and $cliente.Connected
    } catch {
        return $false
    } finally {
        $cliente.Dispose()
    }
}

function Test-Panel {
    try {
        $pedido = [Net.HttpWebRequest]::Create($Url)
        $pedido.Timeout = 1500
        $pedido.AllowAutoRedirect = $false
        $respuesta = $pedido.GetResponse()
        $codigo = [int]$respuesta.StatusCode
        $respuesta.Dispose()
        return $codigo -eq 200
    } catch [Net.WebException] {
        if ($_.Exception.Response) {
            $codigo = [int]$_.Exception.Response.StatusCode
            $_.Exception.Response.Dispose()
            return $codigo -eq 401
        }
        return $false
    }
}

if (-not (Test-Path -LiteralPath $Ssh)) {
    throw "No encontre OpenSSH en $Ssh"
}

if (-not (Test-PuertoLocal)) {
    $argumentos = @(
        '-N', '-T',
        '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=30',
        '-o', 'ServerAliveCountMax=3',
        '-L', "127.0.0.1:${PuertoLocal}:127.0.0.1:${PuertoRemoto}",
        $Servidor
    )
    $proceso = Start-Process -FilePath $Ssh -ArgumentList $argumentos `
        -WindowStyle Hidden -PassThru
    for ($i = 0; $i -lt 20 -and -not (Test-PuertoLocal); $i++) {
        if ($proceso.HasExited) {
            throw 'No pude abrir el tunel SSH. Revisa la clave SSH del VPS.'
        }
        Start-Sleep -Milliseconds 250
    }
}

if (-not (Test-Panel)) {
    Write-Host 'El panel no respondio; intento recuperarlo...' -ForegroundColor Yellow
    & $Ssh -o BatchMode=yes -o StrictHostKeyChecking=yes $Servidor `
        'systemctl restart wc3-dashboard'
    if ($LASTEXITCODE -ne 0) {
        throw 'No pude reiniciar wc3-dashboard por SSH.'
    }
    Start-Sleep -Seconds 2
}

if (-not (Test-Panel)) {
    throw 'El tunel funciona, pero el dashboard sigue sin responder.'
}

Start-Process $Url
