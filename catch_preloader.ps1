$spf = "C:\Users\epick\Downloads\SP_Flash_Tool_V6.2404\SP_Flash_Tool_V6.2404_Win"
$fx  = "C:\Users\epick\Downloads\flash_x6833b\download_agent\flash.xml"
$auth = "C:\Users\epick\Downloads\X6833B.auth"

$deadline = (Get-Date).AddMinutes(20)
$attempt = 0

while ((Get-Date) -lt $deadline) {
    $attempt++
    $port = $null
    # ищем COM-порт PreLoader VCOM (PID 2000)
    $dev = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
           Where-Object { $_.PNPDeviceID -like "*vid_0e8d*pid_2000*" } |
           Select-Object -First 1
    if ($dev) {
        if ($dev.Name -match "\(COM(\d+)\)") {
            $port = "COM" + $matches[1]
        }
    }

    if ($port) {
        $stamp = (Get-Date).ToString("HH:mm:ss")
        Write-Output "[$stamp] ПОПЫТКА $attempt - поймали PreLoader: $port (устройство: $($dev.Name))"
        $args = @("-f", "`"$fx`"", "-c", "download", "-p", $port, "-a", "`"$auth`"")
        Start-Process -FilePath "$spf\SPFlashToolV6.exe" -ArgumentList $args -Wait -ErrorAction SilentlyContinue
        Write-Output "[$stamp] SP Flash Tool завершился. Проверяем результат..."
        break
    } else {
        Start-Sleep -Milliseconds 400
    }
}

if (-not $port) {
    Write-Output "За 20 минут PreLoader так и не появился. Проверь кабель/порт/драйвер."
}