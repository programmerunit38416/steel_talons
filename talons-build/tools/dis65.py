#!/usr/bin/env python3
"""
dis65.py BIN BASE START END [EQUFILE]  - 65C02 disassembler (a65 syntax)

Also importable: decode(data, base, addr) -> (length, mnemonic, mode, value)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a65 import OPS  # noqa: E402

DEC = {}
for _m, _modes in OPS.items():
    for _md, _c in _modes.items():
        DEC[_c] = (_m, _md)
SIZE = dict(imp=1, acc=1, imm=2, zp=2, zpx=2, zpy=2, izx=2, izy=2, izp=2, rel=2,
            abs=3, abx=3, aby=3, ind=3, aix=3)


def decode(data, base, addr):
    op = data[addr - base]
    if op not in DEC:
        return 1, None, None, op
    m, md = DEC[op]
    n = SIZE[md]
    if addr - base + n > len(data):
        return 1, None, None, op
    if n == 2:
        v = data[addr - base + 1]
        if md == 'rel':
            v = (addr + 2 + (v - 256 if v > 127 else v)) & 0xFFFF
    elif n == 3:
        v = data[addr - base + 1] | data[addr - base + 2] << 8
    else:
        v = None
    return n, m, md, v


def fmt(m, md, v, name=lambda v, w: '$%0*X' % (w, v)):
    if md in ('imp',):
        return m
    if md == 'acc':
        return m + '\tA'
    if md == 'imm':
        return m + '\t#$%02X' % v
    w = 2 if md in ('zp', 'zpx', 'zpy', 'izx', 'izy', 'izp') else 4
    s = name(v, w)
    return m + '\t' + {'zp': '%s', 'abs': '%s', 'rel': '%s', 'zpx': '%s,X', 'abx': '%s,X',
                       'zpy': '%s,Y', 'aby': '%s,Y', 'izx': '(%s,X)', 'izy': '(%s),Y',
                       'izp': '(%s)', 'ind': '(%s)', 'aix': '(%s,X)'}[md] % s


def load_equ(path):
    by = {}
    for l in open(path, encoding='latin1'):
        p = l.split()
        if len(p) == 3 and p[1] == 'EQU':
            by.setdefault(int(p[2][1:], 16), []).append(p[0])
    return by


def main():
    binf, base, start, end = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0), int(sys.argv[4], 0)
    data = open(binf, 'rb').read()
    by = load_equ(sys.argv[5]) if len(sys.argv) > 5 else {}

    def name(v, w):
        c = [n for n in by.get(v, []) if not n.isupper() or w == 4] or by.get(v, [])
        return '%s' % c[0] if c and w == 4 else ('$%0*X' % (w, v) + ('{%s}' % c[0] if c else ''))
    a = start
    while a < end:
        for n in by.get(a, []):
            print('%s:' % n)
        n, m, md, v = decode(data, base, a)
        raw = data[a - base:a - base + n].hex()
        print('  %04X  %-8s %s' % (a, raw, fmt(m, md, v, name) if m else '.BYTE $%02X' % v))
        a += n


if __name__ == '__main__':
    main()
