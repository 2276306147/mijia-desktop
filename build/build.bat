@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo [1/3] 检查依赖...
python -c "import PySide6, mijiaAPI" 2>nul
if errorlevel 1 (
    echo 缺少依赖，请先执行： pip install -r requirements.txt -r requirements-build.txt
    exit /b 1
)

echo [2/3] 清理旧产物...
if exist build\work rmdir /s /q build\work
if exist dist\MijiaConsole rmdir /s /q dist\MijiaConsole

echo [3/3] PyInstaller 打包...
python -m PyInstaller build\mijia_desktop.spec --noconfirm --clean --workpath build\work --distpath dist
if errorlevel 1 (
    echo 打包失败
    exit /b 1
)

echo.
echo 完成： dist\MijiaConsole\MijiaConsole.exe
echo 如需安装包，请安装 Inno Setup 后执行：
echo     "%%ProgramFiles(x86)%%\Inno Setup 6\ISCC.exe" build\installer.iss
endlocal
