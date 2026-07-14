# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('.env.example', '.'), ('core', 'core'), ('agents', 'agents'), ('telegram', 'telegram'), ('web', 'web')]
binaries = []
hiddenimports = ['tkinter', 'tkinter.scrolledtext', 'tkinter.ttk', 'asyncio', 'aiohttp', 'aiogram', 'pydantic', 'pydantic_settings', 'python_dotenv', 'sqlalchemy', 'aiosqlite', 'bs4', 'lxml', 'psutil', 'numpy', 'httpx', 'uvicorn', 'fastapi', 'redis', 'beautifulsoup4']
tmp_ret = collect_all('agents.tools')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('core.rag')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['run_desktop.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'PIL', 'pytest', 'notebook', 'jupyter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Everlay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Everlay',
)
