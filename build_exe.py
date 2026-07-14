#!/usr/bin/env python
"""
Build script for Everlay Desktop App using PyInstaller.
Creates standalone executable for Windows/macOS/Linux.
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path


def build_exe():
    """Build standalone executable with PyInstaller."""
    project_root = Path(__file__).parent
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    # Clean previous builds
    for d in [dist_dir, build_dir]:
        if d.exists():
            shutil.rmtree(d)
            print(f"Cleaned {d}")

    # PyInstaller command
    cmd = [
        "pyinstaller",
        "--name=Everlay",
        "--windowed",                   # No console window (GUI app)
        "--icon=assets/icon.ico",       # App icon (create if needed)
        "--add-data=.env.example;.",    # Include .env template as .env
        "--add-data=core;core",         # Include core module
        "--add-data=agents;agents",     # Include agents module
        "--add-data=telegram;telegram", # Include telegram module
        "--add-data=web;web",           # Include web module
        "--hidden-import=tkinter",      # Ensure tkinter included
        "--hidden-import=tkinter.scrolledtext",
        "--hidden-import=tkinter.ttk",
        "--hidden-import=asyncio",
        "--hidden-import=aiohttp",
        "--hidden-import=aiogram",
        "--hidden-import=pydantic",
        "--hidden-import=pydantic_settings",
        "--hidden-import=python_dotenv",
        "--hidden-import=sqlalchemy",
        "--hidden-import=aiosqlite",
        "--hidden-import=bs4",
        "--hidden-import=lxml",
        "--hidden-import=psutil",
        "--hidden-import=numpy",
        "--hidden-import=httpx",
        "--hidden-import=uvicorn",
        "--hidden-import=fastapi",
        "--hidden-import=redis",
        "--hidden-import=beautifulsoup4",
        "--collect-all=agents.tools",   # Include all tools
        "--collect-all=core.rag",       # Include RAG
        "--exclude-module=matplotlib",  # Exclude heavy unused deps
        "--exclude-module=PIL",
        "--exclude-module=pytest",
        "--exclude-module=notebook",
        "--exclude-module=jupyter",
        "--clean",
        "run_desktop.py",
    ]

    # Adjust paths for current OS
    if sys.platform == "win32":
        # Windows: use semicolon for add-data separator (already correct)
        pass
    else:
        # macOS/Linux: use colon for add-data separator
        cmd = [c.replace(";", ":") for c in cmd]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        exe_path = dist_dir / ("Everlay.exe" if sys.platform == "win32" else "Everlay")
        print(f"\nBuild successful!")
        print(f"Executable: {exe_path}")
        print(f"Size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print(f"\nBuild failed with code {result.returncode}")
        sys.exit(1)


def create_icon():
    """Create a simple icon if not exists."""
    icon_path = Path(__file__).parent / "assets" / "icon.ico"
    if not icon_path.exists():
        icon_path.parent.mkdir(exist_ok=True)
        # Create a simple colored square as placeholder
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGBA', (256, 256), (30, 30, 30, 255))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([32, 32, 224, 224], radius=32, fill=(78, 201, 176, 255))
            draw.text((100, 110), "EV", fill=(30, 30, 30, 255), font_size=80)
            img.save(icon_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
            print(f"Created placeholder icon: {icon_path}")
        except ImportError:
            print("Pillow not installed, skipping icon creation. Install with: pip install pillow")


if __name__ == "__main__":
    create_icon()
    build_exe()