# Corrida semanal de concursos públicos: la lanza la tarea programada "Encuentra Empleo - concursos semanal".
# Abre el Chrome de abrir_chrome.ps1, te pide iniciar sesión (el script nunca la inicia), corre publicas.py
# y después historial.py, que actualiza salida/frecuencia_ti.xlsx. Si la sesión caduca, te vuelve a pedir
# iniciar sesión y continúa donde quedó (hasta 3 intentos).
Set-Location $PSScriptRoot
Add-Type -AssemblyName System.Windows.Forms
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$log = Join-Path $PSScriptRoot "salida\datos\log_semanal.txt"
$env:PYTHONIOENCODING = "utf-8"

function Aviso($texto, $botones = "OKCancel") {
    [System.Windows.Forms.MessageBox]::Show($texto, "Encuentra Empleo - concursos semanal", $botones,
        [System.Windows.Forms.MessageBoxIcon]::Information)
}

function ChromeAbierto {
    try { $c = New-Object System.Net.Sockets.TcpClient("127.0.0.1", 9222); $c.Close(); $true } catch { $false }
}

"`n===== $(Get-Date -Format 'yyyy-MM-dd HH:mm') =====" | Out-File $log -Append -Encoding utf8
if (-not (ChromeAbierto)) {
    & (Join-Path $PSScriptRoot "abrir_chrome.ps1")
    Start-Sleep -Seconds 5
}

$completo = $false
for ($intento = 1; $intento -le 3 -and -not $completo; $intento++) {
    $r = Aviso ("Inicia sesión como aspirante en la ventana de Chrome de Encuentra Empleo y pulsa Aceptar.`n`n" +
                "Tarda unos 20 minutos; no cierres Chrome. Cancelar = saltar esta semana.")
    if ($r -ne "OK") { "Saltada por el usuario" | Out-File $log -Append -Encoding utf8; exit }
    $salida = & $python -u publicas.py 2>&1 | ForEach-Object { "$_" }
    $salida | Out-File $log -Append -Encoding utf8
    $texto = $salida -join "`n"
    $completo = -not ($texto -match "La sesión caducó|No hay sesión activa|No encuentro Chrome")
}

& $python -u subir_bases.py 2>&1 | ForEach-Object { "$_" } | Out-File $log -Append -Encoding utf8
$resumen = & $python -u historial.py 2>&1 | ForEach-Object { "$_" }
$resumen | Out-File $log -Append -Encoding utf8
$estado = if ($completo) { "Corrida completa." } else { "La corrida quedó incompleta (la sesión caducó 3 veces); la próxima continúa donde quedó." }
Aviso "$estado`n`n$($resumen -join "`n")`n`nRevisa salida\frecuencia_ti.xlsx" "OK" | Out-Null
