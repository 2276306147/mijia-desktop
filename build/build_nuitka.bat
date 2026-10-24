@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo === 米家控制台 · Nuitka 构建 ===
echo 依赖： pip install -r requirements.txt nuitka ordered-set zstandard
echo 需要在 Windows 上运行（Nuitka 不支持交叉编译）

python -m nuitka ^
  --standalone ^
  --assume-yes-for-downloads ^
  --enable-plugin=pyside6 ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=app\resources\app.ico ^
  --company-name=MijiaDesktop ^
  --product-name=MijiaConsole ^
  --file-version=1.0.0.0 ^
  --product-version=1.0.0.0 ^
  --file-description="Mijia Console" ^
  --include-data-dir=app\resources=resources ^
  --include-package=mijiaAPI ^
  --include-package=Crypto ^
  --include-package=qrcode ^
  --nofollow-import-to=tkinter,matplotlib,numpy,pandas,scipy,IPython ^
  --output-dir=dist-nuitka ^
  --output-filename=MijiaConsole.exe ^
  --remove-output ^
  run.py

if errorlevel 1 (
    echo.
    echo 构建失败。若提示缺少编译器，请安装 Visual Studio Build Tools，
    echo 或改用： --mingw64 --assume-yes-for-downloads
    exit /b 1
)

echo.
echo 完成： dist-nuitka\run.dist\MijiaConsole.exe
echo 该目录整体即为绿色版，可打包为 zip 分发。
endlocal
