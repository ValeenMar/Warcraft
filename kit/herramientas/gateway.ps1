# ===========================================================================
# gateway.ps1 - agrega el servidor a la lista de Battle.net de Warcraft III
# ---------------------------------------------------------------------------
# La lista vive en el registro, en:
#   HKCU\Software\Blizzard Entertainment\Warcraft III
#   valor "Battle.net Gateways", tipo REG_MULTI_SZ
#
# El formato (sacado del instalador oficial de PvPGN,
# github.com/pvpgn/battle.net-gateway-installer) es:
#
#   elemento 0 : "1001"          <- version del formato
#   elemento 1 : "NN"            <- indice, con dos digitos, del server elegido
#   despues, de a tres por cada servidor: direccion, huso horario, titulo
#
# Se agrega sin borrar los servidores que ya estaban, y se deja el nuestro
# como el seleccionado para que el jugador no tenga que buscarlo en la lista.
# Es idempotente: correrlo dos veces no duplica nada.
# ===========================================================================
param(
    [Parameter(Mandatory = $true)][string]$Ip,
    [Parameter(Mandatory = $true)][string]$Tz,
    [Parameter(Mandatory = $true)][string]$Title
)

$ErrorActionPreference = 'Stop'
$key = 'HKCU:\Software\Blizzard Entertainment\Warcraft III'
$name = 'Battle.net Gateways'

# --- leer lo que ya haya -----------------------------------------------------
$list = $null
try {
    $raw = (Get-ItemProperty -Path $key -Name $name -ErrorAction Stop).$name
    if ($raw -is [string[]] -and $raw.Count -ge 2) { $list = [System.Collections.ArrayList]@($raw) }
} catch {
    # La clave o el valor no existen todavia: arrancamos de cero mas abajo.
}
if ($null -eq $list) {
    # Mismo valor por defecto que usa el instalador oficial cuando no hay nada.
    $list = [System.Collections.ArrayList]@('1001', '00')
}

# --- agregar el server si no estaba -----------------------------------------
$pos = $list.IndexOf($Ip)
if ($pos -lt 2) {
    [void]$list.Add($Ip)
    [void]$list.Add($Tz)
    [void]$list.Add($Title)
    $pos = $list.Count - 3
    Write-Host "        OK: `"$Title`" agregado a la lista"
} else {
    Write-Host "        Ya estaba en la lista, no lo duplico"
}

# --- dejarlo seleccionado ----------------------------------------------------
# Los servidores empiezan en el elemento 2 y ocupan 3 lugares cada uno.
$indice = [int](($pos - 2) / 3) + 1
$list[1] = '{0:00}' -f $indice

if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
Set-ItemProperty -Path $key -Name $name -Value ([string[]]$list) -Type MultiString
Write-Host "        OK: queda elegido por defecto (numero $indice)"
