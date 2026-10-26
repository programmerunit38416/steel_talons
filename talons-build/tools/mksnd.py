#!/usr/bin/env python3
"""
mksnd.py SRCDIR KITDIR

One-time recovery of the Handy sound drivers (HSFX.SRC, HMUSIC.SRC, HSFX.VAR,
HMUSIC.VAR) from the sound region of the shipped TALONS.BIN, using the
symbol values in TALONS.EQU.  A few address constants that the tracer cannot
recognise are patched to symbolic form below.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkkit  # noqa: E402

SRC, K = sys.argv[1], sys.argv[2]
values, _order, game = mkkit.load(SRC)
_sys, (LO, HI) = mkkit.regions(values, game)
eq = {}
for n, v in values.items():
    eq.setdefault(v, []).append(n)
skip = ('audio_offsets', 'DEFS', 'HSFX_HMUSIC_AREA@')
O = tempfile.mkdtemp()
with open(os.path.join(O, 'ORIG.EQU'), 'w') as f:
    f.writelines('%s EQU $%04X\n' % (n, v) for n, v in values.items())
with open(os.path.join(O, 'game.syms'), 'w') as f:
    f.write('\n'.join(sorted(game)) + '\n')
# trace from every label in the driver code (it ends where the voice data
# tables start)
code_end = values['voice_offsets']
ents = [n for v in sorted(eq) if LO <= v < code_end for n in eq[v] if n not in skip]
subprocess.check_call([sys.executable, '-I', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recover.py'),
                       os.path.join(SRC, 'TALONS.BIN'), '0x%X' % (values['STARTPGM@'] - 6),
                       '0x%X' % LO, '0x%X' % HI,
                       os.path.join(O, 'ORIG.EQU'), os.path.join(O, 'game.syms'),
                       os.path.join(O, 'snd.src')] + ents)
src = open(os.path.join(O, 'snd.src')).read().split('\n')
a, b = src.index('InitHMusic'), src.index('HSFXVarStart')
hsfx = [l for l in src[:a] if l != 'HSFX_HMUSIC_AREA@']
hmus = src[a:b]


def varblock(lo, hi, title, end):
    names = sorted((v, n) for v, ns in eq.items() for n in ns if lo <= v < hi and n not in ('DEFS', end))
    out = ['*', '* %s (reconstructed from the Steel Talons binary)' % title, '*',
           '* Driver variables, linked into the code image (initial value $FF).', '*']
    addrs = sorted(set(v for v, n in names))
    for i, v in enumerate(addrs):
        nxt = addrs[i + 1] if i + 1 < len(addrs) else hi
        ns = [n for vv, n in names if vv == v]
        out += ns[:-1]
        out.append('%-16s BLKB\t%d,$FF' % (ns[-1], nxt - v))
    return out + [end]


def hdr(t, d):
    return ['*', '* %s (reconstructed from the Steel Talons binary)' % t, '*', '* ' + d, '*']


text = '\n'.join(hmus)
for a_, b_ in [("""		LDX	#$90
L93B3
		STZ	launch_channel+3,X""", """		LDX	#HMusicVarEnd-HMusicVarStart
L93B3
		STZ	HMusicVarStart-1,X		;CLEAR MUSIC VARIABLES"""),
               ("""		LDA	#$B1
		STA	$010C
		LDA	#$94
		STA	$010D""", """		LDA	#<hmusic_driver			;HOOK TIMER 6 INTERRUPT
		STA	sysIntTable+(6*2)
		LDA	#>hmusic_driver
		STA	sysIntTable+(6*2)+1"""),
               ("""		ADC	#$B3
		LDX	#$98""", """		ADC	#<attackframe_v0
		LDX	#>attackframe_v0""")]:
    assert a_ in text, a_
    text = text.replace(a_, b_)
open(os.path.join(K, 'HSFX.SRC'), 'w').write('\n'.join(hdr('HSFX.SRC', 'Handy sound effects driver.') + hsfx) + '\n')
open(os.path.join(K, 'HMUSIC.SRC'), 'w').write('\n'.join(hdr('HMUSIC.SRC', 'Handy music driver (runs from the timer 6 interrupt, see InitHMusic).')) + '\n' + text + '\n')
open(os.path.join(K, 'HSFX.VAR'), 'w').write('\n'.join(varblock(values['HSFXVarStart'], values['HMusicVarStart'], 'HSFX.VAR', 'HSFXVarEnd')) + '\n')
open(os.path.join(K, 'HMUSIC.VAR'), 'w').write('\n'.join(varblock(values['HMusicVarStart'], HI, 'HMUSIC.VAR', 'HMusicVarEnd')) + '\n')
