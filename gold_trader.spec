# PyInstaller spec - MT5 Aranykereskedő Bot asztali alkalmazás
# Build: pyinstaller gold_trader.spec
# Előtte: pip install pyinstaller customtkinter

import sys

try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules
    _ctk_datas = collect_data_files('customtkinter')
    _pydantic_hidden = list(collect_submodules('pydantic'))
    try:
        _pydantic_hidden += list(collect_submodules('pydantic_core'))
    except Exception:
        pass
except Exception:
    _ctk_datas = []
    _pydantic_hidden = []

block_cipher = None

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=_ctk_datas,
    hiddenimports=[
        'customtkinter',
        'src',
        'src.config',
        'src.mt5_client',
        'src.strategy_base',
        'pydantic',
        'pydantic_core',
        'MetaTrader5',
    ] + _pydantic_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['streamlit'],  # nem kell a böngészős verzióhoz
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MT5 Gold Trader Bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # ne jelenjen meg konzol ablak
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Egy mappás verzió (exe + függőségek): onefile=False helyett colllect
# Ha onefile=True-t használnál, egyetlen .exe készül, de lassabban indul (kicsomagolás).
# Jelenleg onefile=False nincs megadva, ezért PyInstaller alapértelmezett: onefile=True.
# Egy exe készül - egyszerűbb terjesztés. Ha lassú az indulás, cseréld Analysis + exe helyett
# FELTÉTELESEN: exe = EXE(..., onefile=False) és COLLECT(exe, ...) - akkor mappa készül sok fájllal.
