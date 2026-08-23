@echo off
chcp 65001 >nul
cd /d C:\Users\epick\Downloads\flash_x6833b
"C:\Users\epick\Downloads\antumbra.exe" -c -v pgpt -d "C:\Users\epick\Downloads\flash_x6833b\DA_BR.bin" -p "C:\Users\epick\Downloads\flash_x6833b\preloader_x6833b_h894.bin" -a "C:\Users\epick\Downloads\X6833B.auth" --usb-log > "C:\Users\epick\Downloads\flash_x6833b\pgpt2.log" 2> "C:\Users\epick\Downloads\flash_x6833b\pgpt2.err"
echo EXITCODE=%ERRORLEVEL% >> "C:\Users\epick\Downloads\flash_x6833b\pgpt2.log"