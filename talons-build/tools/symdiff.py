#!/usr/bin/env python3
"""symdiff.py ORIG.EQU NEW.SYM - list symbols whose values differ, by address"""
import sys
def load(p):
    d = {}
    for l in open(p, encoding='latin1'):
        x = l.split()
        if len(x) == 3 and x[1] == 'EQU':
            d[x[0]] = int(x[2][1:], 16)
    return d
a, b = load(sys.argv[1]), load(sys.argv[2])
diff = sorted((a[k], k, b[k]) for k in a if k in b and a[k] != b[k])
missing = sorted(k for k in a if k not in b)
for v, k, nv in diff[:int(sys.argv[3]) if len(sys.argv) > 3 else 15]:
    print('%-24s orig $%04X  new $%04X  (%+d)' % (k, v, nv, nv - v))
print('%d differ, %d missing: %s' % (len(diff), len(missing), ' '.join(missing[:30])))
