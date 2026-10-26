#!/usr/bin/env python3
"""
recover.py BIN BASE LO HI EQUFILE GAMESYMS OUT [ENTRY...]

Tracing disassembler used to recover dev-kit library code that was linked
into TALONS.BIN but whose source is missing.  Code is found by following
control flow from the given entry labels; everything else becomes .BYTE
data.  Operands that point inside [LO,HI) become labels so the result is
relocatable; other operands use the symbol table.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dis65 import decode  # noqa: E402

binf, base, lo, hi, equf, gamef, outf = sys.argv[1:8]
entries = sys.argv[8:]
base, lo, hi = int(base, 0), int(lo, 0), int(hi, 0)
data = open(binf, 'rb').read()

byval = {}
byname = {}
for l in open(equf, encoding='latin1'):
    p = l.split()
    if len(p) == 3 and p[1] == 'EQU':
        v = int(p[2][1:], 16)
        byval.setdefault(v, []).append(p[0])
        byname[p[0]] = v
game = set(l.strip() for l in open(gamef))

labels = {}
for v, ns in byval.items():
    if lo <= v < hi:
        ks = [n for n in ns if n not in game]
        if ks:
            labels[v] = ks

code = {}
todo = [byname[e] for e in entries]
while todo:
    a = todo.pop()
    while lo <= a < hi and a not in code:
        n, m, md, v = decode(data, base, a)
        if m is None:
            print('warning: bad opcode at $%04X' % a, file=sys.stderr)
            break
        code[a] = (n, m, md, v)
        if md == 'rel' or (m in ('JSR', 'JMP') and md == 'abs'):
            if lo <= v < hi:
                todo.append(v)
                labels.setdefault(v, [])
        if m in ('RTS', 'RTI', 'BRA', 'JMP', 'BRK'):
            break
        a += n

covered = set()
for a, (n, *_r) in code.items():
    covered.update(range(a, a + n))

# data references inside the region are written as label+offset; only
# references to code get labels of their own
for a, (n, m, md, v) in code.items():
    if md not in ('imp', 'acc', 'imm', 'rel') and v is not None and v in code:
        labels.setdefault(v, [])
gen = {}


def lab(v):
    if labels.get(v):
        return labels[v][0]
    if v not in gen:
        gen[v] = 'L%04X' % v
    return gen[v]


def symname(v, zp):
    if lo <= v < hi:
        # point at the nearest label at or below v
        b = v
        while b > lo and not labels.get(b):
            b -= 1
        return lab(b) + ('+%d' % (v - b) if v != b else '')
    gamerange = 0x2000 <= v < 0xFC00

    def cands(x):
        ns = byval.get(x, [])
        own = [n for n in ns if (n in game) == gamerange]
        return own
    if cands(v):
        return cands(v)[0]
    for d in range(1, 8):
        if cands(v - d):
            return '%s+%d' % (cands(v - d)[0], d)
    return '$%0*X' % (2 if zp else 4, v)


out = []
a = lo
while a < hi:
    if a in labels:
        for nm in labels[a] or [lab(a)]:
            out.append(nm)
    elif a in gen:
        out.append(gen[a])
    if a in code:
        n, m, md, v = code[a]
        if md in ('imp',):
            s = m
        elif md == 'acc':
            s = m + '\tA'
        elif md == 'imm':
            s = m + '\t#$%02X' % v
        elif md == 'rel':
            s = m + '\t' + lab(v)
        else:
            zp = md in ('zp', 'zpx', 'zpy', 'izx', 'izy', 'izp')
            nm = symname(v, zp)
            fmt = {'zp': '%s', 'abs': '%s', 'zpx': '%s,X', 'abx': '%s,X', 'zpy': '%s,Y',
                   'aby': '%s,Y', 'izx': '(%s,X)', 'izy': '(%s),Y', 'izp': '(%s)',
                   'ind': '(%s)', 'aix': '(%s,X)'}[md]
            s = m + '\t' + fmt % nm
        out.append('\t\t' + s)
        a += n
    else:
        e = a + 1
        while e < hi and e not in code and e not in labels and e not in gen and e - a < 8:
            e += 1
        out.append('\t\t.BYTE\t' + ','.join('$%02X' % b for b in data[a - base:e - base]))
        a = e

open(outf, 'w').write('\n'.join(out) + '\n')
print('code bytes %d of %d; %d generated labels' % (len(covered), hi - lo, len(gen)), file=sys.stderr)
