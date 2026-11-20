# -*- mode: python ; coding: utf-8 -*-
# 星剪 StarSnip — PyInstaller 打包配置

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
hiddenimports = []
for pkg in ("customtkinter", "darkdetect"):
    datas += collect_data_files(pkg)
    hiddenimports += collect_submodules(pkg)

# 应用图标与品牌资源随包带上（源码运行从仓库根 assets/ 读取）
datas += [("assets", "assets")]

a = Analysis(
    ['starsnip_launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='StarSnip',
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
    icon='assets/starsnip.ico',
)
