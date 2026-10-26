#!/usr/bin/env python3
"""
mkkit.py SRCDIR KITDIR

One-time generator for the reconstructed Lynx dev-kit equates.  The original
\\PR\\LYNX\\INCLUDE files were not shipped with the Steel Talons source, but
the game was linked with GLOBALS ON so TALONS.EQU (generated from TALONS.SYM)
holds the value of every kit symbol.  This writes the equates that are not
defined anywhere in the game sources into KITDIR/KITEQU.I.
"""
import glob
import os
import re
import sys

ZPVARS = ('sysptr', 'sysptr2', 'sysptr3')     # defined by SYSZPAGE.SRC


def load(src):
    """Return (values, names in file order, names defined by the game sources)."""
    game = set()
    for f in glob.glob(os.path.join(src, '*')):
        if f.split('.')[-1].upper() in ('ASM', 'INC', 'HCR', 'SCB', 'PAL'):
            for l in open(f, encoding='latin1').read().replace('\r', '').split('\n'):
                m = re.match(r'^([A-Za-z_@?.][A-Za-z0-9_@?#.]*)', l)
                if m:
                    game.add(m.group(1).rstrip(':'))
    eq, order = {}, []
    for l in open(os.path.join(src, 'TALONS.EQU'), encoding='latin1'):
        p = l.split()
        if len(p) == 3 and p[1] == 'EQU':
            eq[p[0]] = int(p[2][1:], 16)
            order.append(p[0])
    return eq, order, game


def regions(eq, game):
    """Address ranges of kit code/data linked into TALONS.BIN."""
    sys_lo = eq['SYSTEMAREA@']
    sys_hi = min(v for k, v in eq.items() if k in game and v > sys_lo and k != 'SYSTEMAREA@')
    return (sys_lo, sys_hi), (eq['HSFX_HMUSIC_AREA@'], eq['PAST_HSFX_HMUSIC@'])


def main():
    src, kit = sys.argv[1], sys.argv[2]
    eq, order, game = load(src)
    (sys_lo, sys_hi), (snd_lo, snd_hi) = regions(eq, game)
    out = []
    for k in sorted((k for k in order if k not in game), key=lambda k: (eq[k], k)):
        v = eq[k]
        # labels inside the kit regions are defined by the reconstructed .SRC
        # and .VAR files (HMusicVarEnd sits on the end of the sound region)
        if k in ZPVARS or sys_lo <= v < sys_hi or snd_lo <= v <= snd_hi:
            continue
        out.append('%-24s EQU\t$%04X' % (k, v))
    with open(os.path.join(kit, 'KITEQU.I'), 'w') as f:
        f.write('*\n* KITEQU.I - Lynx dev-kit equates recovered from TALONS.SYM\n*\n')
        f.write('\n'.join(out) + '\n')
    print('%d kit equates; sys region $%04X-$%04X, sound region $%04X-$%04X'
          % (len(out), sys_lo, sys_hi, snd_lo, snd_hi))


if __name__ == '__main__':
    main()
