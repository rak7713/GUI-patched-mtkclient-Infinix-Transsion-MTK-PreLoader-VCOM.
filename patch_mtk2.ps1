$ErrorActionPreference = "Continue"
$mtkdir = "C:\Users\epick\Downloads\mtkclient-2.1.4.1\mtkclient-2.1.4.1"
$workdir = "C:\Users\epick\Downloads\flash_x6833b\mtkwork"
$loader = "C:\Users\epick\Downloads\flash_x6833b\fw_test\v240502V576\download_agent\DA_BR.bin"
$vb     = "C:\Users\epick\Downloads\flash_x6833b\fw_test\v240502V576\vendor_boot.img"
$logout = "C:\Users\epick\Downloads\flash_x6833b\mtkwork\run.out"
$logerr = "C:\Users\epick\Downloads\flash_x6833b\mtkwork\run.err"
$overall = "C:\Users\epick\Downloads\flash_x6833b\mtkwork\mtk_final.log"

$deadline = (Get-Date).AddMinutes(25)
$attempt = 0

while ((Get-Date) -lt $deadline) {
    $attempt++
    $port = $null
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
        Remove-Item "$workdir\hwparam.json" -Force -ErrorAction SilentlyContinue
        Remove-Item $logout,$logerr -Force -ErrorAction SilentlyContinue
        Write-Output "[$stamp] ATTEMPT $attempt - PreLoader на $port, запуск mtkclient"
        $p = Start-Process -FilePath "python" -ArgumentList @("$mtkdir\mtk.py","w","vendor_boot_a","$vb","--loader","$loader","--serialport",$port,"--loglevel","1") -WorkingDirectory $workdir -RedirectStandardOutput $logout -RedirectStandardError $logerr -PassThru -NoNewWindow
        $handshaked = $false
        $deadlineAttempt = (Get-Date).AddSeconds(180)
        $result = $null
        while ((Get-Date) -lt $deadlineAttempt) {
            Start-Sleep -Milliseconds 500
            if ($p.HasExited) { $result = $p.ExitCode; break }
            $tail = ""
            foreach ($f in @($logout,$logerr)) { if (Test-Path $f) { $tail += Get-Content $f -Raw -ErrorAction SilentlyContinue } }
            if (-not $handshaked -and $tail -match "Handshake successful") {
                $handshaked = $true
                Write-Output "[$stamp] Handshake OK, ждём загрузку DA и запись (до 3 мин)..."
            }
            if ($tail -match "Wrote .*to sector") {
                Write-Output "[$stamp] !!! WRITE OK - vendor_boot записан !!!"
                Add-Content $overall "[$stamp] WRITE OK - vendor_boot записан (attempt $attempt)"
                $result = "WRITEOK"
                break
            }
            if ($tail -match "Error:|Failed|Locked|not accepted|status error|SLA Key wasn") {
                # возможная ошибка после handshake - дадим дочитать, но если это про запись - стоп
                if ($handshaked -and $tail -match "Locked|status:|Error") {
                    Write-Output "[$stamp] Ошибка после handshake:"
                    ($tail -split "`n" | Select-Object -Last 25)
                    Add-Content $overall "[$stamp] Ошибка после handshake (attempt $attempt)"
                    $result = "ERR"
                    break
                }
            }
        }
        if ($result -eq "WRITEOK") { break }
        if ($result -eq $null -and $handshaked) {
            Write-Output "[$stamp] Процесс ещё жив после 3 мин. Убиваю."
        }
        $tail = ""
        foreach ($f in @($logout,$logerr)) { if (Test-Path $f) { $tail += Get-Content $f -Raw -ErrorAction SilentlyContinue } }
        if ($tail -match "Wrote .*to sector") {
            Write-Output "[$stamp] !!! WRITE OK (по хвосту) !!!"
            Add-Content $overall "[$stamp] WRITE OK (по хвосту, attempt $attempt)"
            break
        }
        if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 200
    } else {
        Start-Sleep -Milliseconds 250
    }
}
Write-Output "== Цикл завершён. Полный лог: $overall =="