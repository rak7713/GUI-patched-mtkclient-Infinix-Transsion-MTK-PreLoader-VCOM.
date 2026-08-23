$ErrorActionPreference = "Continue"
$mtkdir = "C:\Users\epick\Downloads\mtkclient-2.1.4.1\mtkclient-2.1.4.1"
$workdir = "C:\Users\epick\Downloads\flash_x6833b\mtkwork"
$loader = "C:\Users\epick\Downloads\flash_x6833b\fw_test\v240502V576\download_agent\DA_BR.bin"
$vb     = "C:\Users\epick\Downloads\flash_x6833b\fw_test\v240502V576\vendor_boot.img"
$log    = "C:\Users\epick\Downloads\flash_x6833b\patch_log.txt"

$deadline = (Get-Date).AddMinutes(30)
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
        Write-Output "[$stamp] Attempt $attempt - PreLoader on $port ($($dev.Name))"
        Push-Location $workdir
        & python "$mtkdir\mtk.py" w vendor_boot_a $vb --loader $loader --serialport $port --loglevel 1 2>&1 | Tee-Object -FilePath $log -Append
        Pop-Location
        $code = $LASTEXITCODE
        Write-Output "[$stamp] mtkclient exit code: $code"
        # Проверяем успех: признак записи найден
        if (Select-String -Path $log -Pattern "Wrote .*vendor_boot.*to sector|Wrote .*to sector" -Quiet) {
            Write-Output "[$stamp] !!! WRITE OK, прерываю цикл !!!"
            break
        }
        Start-Sleep -Milliseconds 1500
    } else {
        Start-Sleep -Milliseconds 300
    }
}
Write-Output "== Done. See $log =="