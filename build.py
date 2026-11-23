"""把 滑鼠連點器.pyw 打包成單一 exe。

用法：直接點兩下 build.bat，或執行  py build.py
資料夾裡如果有 icon.ico，會自動當成 exe 和視窗的圖示。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "滑鼠連點器"
SOURCE = HERE / f"{NAME}.pyw"
ICON = HERE / "icon.ico"
WORK = HERE / "build"


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("正在安裝 PyInstaller…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--onefile", "--windowed",
        "--name", NAME,
        "--distpath", str(HERE),
        "--workpath", str(WORK),
        "--specpath", str(WORK),
    ]
    if ICON.exists():
        print("使用圖示：icon.ico")
        args += ["--icon", str(ICON), "--add-data", f"{ICON}{os.pathsep}."]
    else:
        print("找不到 icon.ico，使用預設圖示")
    args.append(str(SOURCE))

    subprocess.check_call(args)
    shutil.rmtree(WORK, ignore_errors=True)
    print(f"\n完成！exe 在：{HERE / (NAME + '.exe')}")


if __name__ == "__main__":
    main()
