#!/usr/bin/env python3
"""
build.py - build Steel Talons (Atari Lynx) from source.

    python3 build.py [--src DIR] [--out DIR] [--verify]

Replaces the original DOS pipeline (MAKE A.BAT -> X6502/XLINK/XASM/DATA2ASM/
SYM2EQU/LYNXROM) with the Python tools in tools/:

  COMPLETE.DNL  -> COMPLETE.ASM                      (data2asm)
  TALONS.ASM    -> TALONS.BIN + TALONS.EQU           (a65, main program)
  overlays      -> HISCORE/ATRACT/SELECT/.. .BIN     (a65, use TALONS.EQU)
  data modules  -> TITLE/CREDITS/M?/TR/EXPLODE?.BIN  (a65)
  sprite .HCR   -> PF?/PFTR/TRM/M?M.BIN              (a65 + BIN header)
  TALONS.HSF    -> TALONS.ROM                        (lynxrom)
  TALONS.ROM    -> STEELTALONS.lnx                   (+ boot loader, LNX header)

--verify compares every output with the prebuilt copy shipped in the source
directory.
"""
import argparse
import filecmp
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, 'tools')

OVERLAYS = ['HISCORE', 'ATRACT', 'SELECT', 'MOVEMENT', 'PASSFAIL', 'DEBRIEF', 'SHOWMAP']
DATA = (['TITLE', 'CREDITS', 'TR'] + ['M%s' % c for c in '123456789ABC']
        + ['EXPLODE%d' % i for i in range(1, 9)])
SPRITES = (['PF%s' % c for c in '123456789ABC'] + ['PFTR', 'TRM']
           + ['M%sM' % c for c in '123456789ABC'])


def run(*args):
    r = subprocess.run([sys.executable, '-I'] + list(args))
    if r.returncode:
        sys.exit(r.returncode)


def a65(src, out, inc, *extra):
    run(os.path.join(TOOLS, 'a65.py'), src, '-o', out, *sum((['-I', d] for d in inc), []), *extra)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--src', default=os.path.join(HERE, '..', 'finalsrc'))
    ap.add_argument('--out', default=os.path.join(HERE, 'build'))
    ap.add_argument('--verify', action='store_true')
    a = ap.parse_args()
    src, out = os.path.abspath(a.src), os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    inc = [out, src]
    S = lambda n: os.path.join(src, n)  # noqa: E731
    O = lambda n: os.path.join(out, n)  # noqa: E731

    print('COMPLETE.ASM')
    with open(S('COMPLETE.DNL'), 'rb') as fi, open(O('COMPLETE.ASM'), 'wb') as fo:
        r = subprocess.run([sys.executable, '-I', os.path.join(TOOLS, 'data2asm.py')], stdin=fi, stdout=fo)
        if r.returncode:
            sys.exit(r.returncode)

    print('TALONS.BIN')
    a65(S('TALONS.ASM'), O('TALONS.BIN'), inc, '--sym', O('TALONS.EQU'))

    for n in OVERLAYS + DATA:
        print(n + '.BIN')
        a65(S(n + '.ASM'), O(n + '.BIN'), inc)

    for n in SPRITES:
        print(n + '.BIN')
        a65(S(n + '.HCR'), O(n + '.RAW'), inc)
        data = open(O(n + '.RAW'), 'rb').read()
        os.remove(O(n + '.RAW'))
        # XASM: load record (01 addr) + data record (12 len data) + end (00)
        open(O(n + '.BIN'), 'wb').write(b'\x01\x00\x00\x12' + struct.pack('<H', len(data)) + data + b'\x00')

    print('TALONS.ROM')
    run(os.path.join(TOOLS, 'lynxrom.py'), S('TALONS.HSF'), O('TALONS.ROM'), '-I', out)

    print('STEELTALONS.lnx')
    a65(os.path.join(HERE, 'boot', 'BOOT2.ASM'), O('BOOT2.BIN'), inc)
    rom = bytearray(open(O('TALONS.ROM'), 'rb').read())
    boot = open(os.path.join(HERE, 'boot', 'STAGE1.BIN'), 'rb').read() + open(O('BOOT2.BIN'), 'rb').read()
    assert len(boot) <= 0x19A and not any(rom[:len(boot)])
    rom[:len(boot)] = boot
    open(O('STEELTALONS.lyx'), 'wb').write(rom)
    hdr = (b'LYNX' + struct.pack('<HHH', 1024, 0, 1) + b'Steel Talons'.ljust(32, b'\0')
           + b'Atari'.ljust(16, b'\0') + b'\0' + b'\0' * 5)
    assert len(hdr) == 64
    open(O('STEELTALONS.lnx'), 'wb').write(hdr + rom)

    if a.verify:
        bad = 0
        names = (['COMPLETE.ASM', 'TALONS.BIN', 'TALONS.ROM']
                 + [n + '.BIN' for n in OVERLAYS + DATA + SPRITES])
        for n in names:
            same = filecmp.cmp(O(n), S(n), shallow=False)
            bad += not same
            if not same:
                print('MISMATCH  %s' % n)
        print('verify: %d of %d outputs identical to the shipped files' % (len(names) - bad, len(names)))
        sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
