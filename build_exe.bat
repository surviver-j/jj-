@echo off
chcp 65001 >nul
setlocal
python --version >nul 2>&1
if errorlevel 1 (
  echo 未检测到 Python，请先安装 Python 3.10 或更高版本。
  pause
  exit /b 1
)
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo PyInstaller 安装失败，请检查网络或使用公司批准的软件源。
  pause
  exit /b 1
)
python -m PyInstaller --noconsole --onefile --clean --name "换线软件同步助手_v0.6" "onekey_change_line_v0.6.py"
if errorlevel 1 (
  echo 打包失败，请检查上方错误信息。
  pause
  exit /b 1
)
echo.
echo 打包完成：dist\换线软件同步助手_v0.6.exe
pause
