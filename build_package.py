#!/usr/bin/env python3
"""Build a Debian APPLaunch installer with package-only tools from Python stdlib."""
import argparse
import io
from pathlib import Path
import struct
import tarfile
import zlib

from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parent
PACKAGE = 'cardputer-js8-lite'
VERSION = '0.3.0'
TARGET = f'{PACKAGE}_{VERSION}_all.deb'
PREFIX = 'usr/share/APPLaunch'
SOURCES = ['pocketjs8_lite.py','radio.py','device.py','diagnostics.py','build_engine.sh',
           'native/modem.cpp','README.md','VALIDATION.md','LICENSE-NOTICE.md','COPYING']

def icon_png():
    im=Image.new('RGB',(96,96),'#0c1719');d=ImageDraw.Draw(im)
    d.rounded_rectangle((6,6,90,90),radius=14,fill='#15282b',outline='#51786c',width=2)
    d.rounded_rectangle((17,20,79,64),radius=3,fill='#0b2423',outline='#4f8678')
    for i,h in enumerate([8,13,20,14,27,23,18,10,14,24,13]):
        x=23+i*5
        d.line((x,52,x,52-h),fill='#ace7ae',width=3)
    d.rounded_rectangle((23,72,73,77),radius=2,fill='#f0c17f')
    bio=io.BytesIO();im.save(bio,format='PNG');return bio.getvalue()

def tar(files):
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz',format=tarfile.GNU_FORMAT) as tf:
        dirs=set()
        for path in files:
            p=Path(path).parent
            while str(p) not in ('.',''):
                dirs.add(p.as_posix());p=p.parent
        for p in sorted(dirs):
            t=tarfile.TarInfo('./'+p+'/');t.type=tarfile.DIRTYPE;t.mode=0o755;t.uid=t.gid=0
            tf.addfile(t)
        for path,(content,mode) in sorted(files.items()):
            t=tarfile.TarInfo('./'+path);t.size=len(content);t.mode=mode;t.uid=t.gid=0
            tf.addfile(t,io.BytesIO(content))
    return buf.getvalue()

def member(name,content):
    head=(f"{name+'/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(content):<10}`\n").encode()
    assert len(head)==60
    return head+content+(b'\n' if len(content)%2 else b'')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir',default=str(ROOT/'dist'))
    args=ap.parse_args()
    for name in SOURCES:
        if not (ROOT/name).is_file():ap.error('Missing '+name)
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    target=out/TARGET
    base=f'{PREFIX}/apps/{PACKAGE}'
    files={}
    for source in SOURCES:
        files[f'{base}/{source}']=((ROOT/source).read_bytes(),0o755 if source.endswith('.sh') else 0o644)
    desktop='[Desktop Entry]\nType=Application\nName=PocketJS8 Lite\nExec=/usr/share/APPLaunch/bin/cardputer-js8-lite\nIcon=share/images/cardputer-js8-lite.png\nTerminal=false\nCategories=HamRadio;\n'
    files[f'{PREFIX}/applications/{PACKAGE}.desktop']=(desktop.encode(),0o644)
    wrapper='#!/bin/sh\nset -eu\numask 077\nexec /usr/bin/python3 /usr/share/APPLaunch/apps/cardputer-js8-lite/pocketjs8_lite.py "$@"\n'
    diagnostic='#!/bin/sh\nset -eu\numask 077\nexec /usr/bin/python3 /usr/share/APPLaunch/apps/cardputer-js8-lite/diagnostics.py "$@"\n'
    build='#!/bin/sh\nset -eu\nexec /usr/share/APPLaunch/apps/cardputer-js8-lite/build_engine.sh "$@"\n'
    files[f'{PREFIX}/bin/{PACKAGE}']=(wrapper.encode(),0o755)
    files[f'{PREFIX}/bin/pocketjs8-lite-check']=(diagnostic.encode(),0o755)
    files[f'{PREFIX}/bin/pocketjs8-lite-build-engine']=(build.encode(),0o755)
    # Also expose diagnostics on PATH, without replacing older PocketJS8 package.
    files['usr/bin/pocketjs8-lite-check']=(diagnostic.encode(),0o755)
    files['usr/bin/pocketjs8-lite-build-engine']=(build.encode(),0o755)
    files[f'{PREFIX}/share/images/{PACKAGE}.png']=(icon_png(),0o644)
    control=(f'Package: {PACKAGE}\nVersion: {VERSION}\nArchitecture: all\n'
             'Maintainer: ProtoV0id local build <local@invalid>\n'
             'Depends: python3 (>= 3.9), python3-pil, python3-evdev, alsa-utils\n'
             'Recommends: git, cmake, build-essential, usbutils\n'
             'Section: hamradio\nPriority: optional\n'
             'Description: PocketJS8 Lite standalone Cardputer Zero terminal\n'
             ' Receiver and deliberate short-message TX interface for DigiRig Mobile and (tr)uSDX.\n'
             ' Native modem built separately from pinned GPL-3.0 source with build script.\n')
    payload=b'!<arch>\n'+member('debian-binary',b'2.0\n')+member('control.tar.gz',tar({'control':(control.encode(),0o644)}))+member('data.tar.gz',tar(files))
    if target.exists():ap.error(f'Installer already exists: {target}')
    target.write_bytes(payload)
    print('Built',target)

if __name__=='__main__':main()
