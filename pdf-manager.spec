# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['F:\\Sandbox\\tenant\\labs-manager\\Iris-kim33\\Code\\labs\\analysis-gateway-kit\\pdf_manager_project\\src\\pdf_manager\\__main__.py'],
    pathex=['F:\\Sandbox\\tenant\\labs-manager\\Iris-kim33\\Code\\labs\\analysis-gateway-kit\\pdf_manager_project\\src'],
    binaries=[],
    datas=[('F:\\Sandbox\\tenant\\labs-manager\\Iris-kim33\\Code\\labs\\analysis-gateway-kit\\pdf_manager_project\\assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pdf-manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['F:\\Sandbox\\tenant\\labs-manager\\Iris-kim33\\Code\\labs\\analysis-gateway-kit\\pdf_manager_project\\assets\\pdf_manager.ico'],
)
