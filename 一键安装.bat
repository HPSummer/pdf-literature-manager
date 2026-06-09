@echo off
echo ========================================
echo  PDF 文献管理器 - 一键安装
echo ========================================
echo.

cd /d "%~dp0"

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 创建虚拟环境...
if not exist ".venv" (
    python -m venv .venv
)

echo [2/4] 安装依赖...
.venv\Scripts\pip.exe install -e ".[dev]" pyinstaller --quiet

echo [3/4] 打包 exe...
.venv\Scripts\pyinstaller.exe --onefile --windowed --name pdf-manager --paths src src\pdf_manager\__main__.py

if not exist "dist\pdf-manager.exe" (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo [4/4] 创建桌面快捷方式...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\pdf文献管理.lnk'); $sc.TargetPath = '%~dp0dist\pdf-manager.exe'; $sc.WorkingDirectory = '%~dp0dist'; $sc.Description = 'PDF 文献管理工具'; $sc.Save()"

echo.
echo ========================================
echo  安装完成！
echo  桌面已生成快捷方式: pdf文献管理.lnk
echo  exe 路径: %~dp0dist\pdf-manager.exe
echo ========================================
pause
