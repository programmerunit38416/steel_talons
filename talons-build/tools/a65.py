#!/usr/bin/env python3
"""
a65 - a cross assembler for the subset of the 2500AD X6502 / XLINK dialect
used by the Steel Talons (Atari Lynx, 1992) sources.

  a65.py SOURCE.ASM -o OUT.BIN [-I dir]... [-k kitdir] [--sym OUT.SYM] [-D NAME=VAL]

The output is the raw image of the CODE section from its lowest to highest
emitted address -- the sources write their own BIN header/trailer bytes, so
this matches what XLINK -X / -XS produced.
"""
import argparse
import os
import re
import sys

IDCH = r'A-Za-z0-9_@?#.'
IDRE = re.compile(r'[A-Za-z_@?.][A-Za-z0-9_@?#.]*')


class AsmError(Exception):
    pass


# --------------------------------------------------------------------------
# 65C02 opcode table: mnemonic -> {mode: opcode}
# modes: imp acc imm zp zpx zpy abs abx aby ind izx izy izp aix rel
# --------------------------------------------------------------------------
OPS = {}


def _op(m, **kw):
    OPS[m] = kw


_op('ADC', imm=0x69, zp=0x65, zpx=0x75, abs=0x6D, abx=0x7D, aby=0x79, izx=0x61, izy=0x71, izp=0x72)
_op('AND', imm=0x29, zp=0x25, zpx=0x35, abs=0x2D, abx=0x3D, aby=0x39, izx=0x21, izy=0x31, izp=0x32)
_op('ASL', acc=0x0A, zp=0x06, zpx=0x16, abs=0x0E, abx=0x1E)
_op('BIT', imm=0x89, zp=0x24, zpx=0x34, abs=0x2C, abx=0x3C)
_op('CMP', imm=0xC9, zp=0xC5, zpx=0xD5, abs=0xCD, abx=0xDD, aby=0xD9, izx=0xC1, izy=0xD1, izp=0xD2)
_op('CPX', imm=0xE0, zp=0xE4, abs=0xEC)
_op('CPY', imm=0xC0, zp=0xC4, abs=0xCC)
_op('DEC', acc=0x3A, zp=0xC6, zpx=0xD6, abs=0xCE, abx=0xDE)
_op('EOR', imm=0x49, zp=0x45, zpx=0x55, abs=0x4D, abx=0x5D, aby=0x59, izx=0x41, izy=0x51, izp=0x52)
_op('INC', acc=0x1A, zp=0xE6, zpx=0xF6, abs=0xEE, abx=0xFE)
_op('JMP', abs=0x4C, ind=0x6C, aix=0x7C)
_op('JSR', abs=0x20)
_op('LDA', imm=0xA9, zp=0xA5, zpx=0xB5, abs=0xAD, abx=0xBD, aby=0xB9, izx=0xA1, izy=0xB1, izp=0xB2)
_op('LDX', imm=0xA2, zp=0xA6, zpy=0xB6, abs=0xAE, aby=0xBE)
_op('LDY', imm=0xA0, zp=0xA4, zpx=0xB4, abs=0xAC, abx=0xBC)
_op('LSR', acc=0x4A, zp=0x46, zpx=0x56, abs=0x4E, abx=0x5E)
_op('ORA', imm=0x09, zp=0x05, zpx=0x15, abs=0x0D, abx=0x1D, aby=0x19, izx=0x01, izy=0x11, izp=0x12)
_op('ROL', acc=0x2A, zp=0x26, zpx=0x36, abs=0x2E, abx=0x3E)
_op('ROR', acc=0x6A, zp=0x66, zpx=0x76, abs=0x6E, abx=0x7E)
_op('SBC', imm=0xE9, zp=0xE5, zpx=0xF5, abs=0xED, abx=0xFD, aby=0xF9, izx=0xE1, izy=0xF1, izp=0xF2)
_op('STA', zp=0x85, zpx=0x95, abs=0x8D, abx=0x9D, aby=0x99, izx=0x81, izy=0x91, izp=0x92)
_op('STX', zp=0x86, zpy=0x96, abs=0x8E)
_op('STY', zp=0x84, zpx=0x94, abs=0x8C)
_op('STZ', zp=0x64, zpx=0x74, abs=0x9C, abx=0x9E)
_op('TRB', zp=0x14, abs=0x1C)
_op('TSB', zp=0x04, abs=0x0C)
for _m, _c in dict(BCC=0x90, BCS=0xB0, BEQ=0xF0, BMI=0x30, BNE=0xD0, BPL=0x10,
                   BRA=0x80, BVC=0x50, BVS=0x70).items():
    _op(_m, rel=_c)
for _m, _c in dict(BRK=0x00, CLC=0x18, CLD=0xD8, CLI=0x58, CLV=0xB8, DEX=0xCA, DEY=0x88,
                   INX=0xE8, INY=0xC8, NOP=0xEA, PHA=0x48, PHP=0x08, PHX=0xDA, PHY=0x5A,
                   PLA=0x68, PLP=0x28, PLX=0xFA, PLY=0x7A, RTI=0x40, RTS=0x60, SEC=0x38,
                   SED=0xF8, SEI=0x78, TAX=0xAA, TAY=0xA8, TSX=0xBA, TXA=0x8A, TXS=0x9A,
                   TYA=0x98).items():
    _op(_m, imp=_c)

ZPFORM = {'abs': 'zp', 'abx': 'zpx', 'aby': 'zpy'}


# --------------------------------------------------------------------------
# expressions
# --------------------------------------------------------------------------
TOKRE = re.compile(r"""
    \s*(?:
      (?P<hex>\$[0-9A-Fa-f]+)
    | (?P<pc>\$)
    | (?P<bin>%[01]+)
    | (?P<dec>[0-9]+)
    | (?P<chr>"(?:[^"]|"")*"|'(?:[^']|'')*')
    | (?P<dop>\.[A-Za-z]+\.)
    | (?P<id>[A-Za-z_@?.][A-Za-z0-9_@?#.]*)
    | (?P<op><>|<=|>=|[-+*/()<>=^\\&|!~])
    )""", re.X)


class Undefined(Exception):
    pass


def tokenize(s):
    out = []
    pos = 0
    s = s.rstrip()
    while pos < len(s):
        m = TOKRE.match(s, pos)
        if not m or m.end() == pos:
            raise AsmError('bad expression: %r' % s)
        pos = m.end()
        k = m.lastgroup
        out.append((k, m.group(k)))
    return out


class Expr:
    """Recursive-descent evaluator.

    precedence (low->high): ^ (or)  .OR.  |  ;  .AND. &  ;  = <> < > <= >= ;
    + - ; * / .MOD. .SHL. .SHR. ; unary - \\ (not) < (low) > (high)
    """

    def __init__(self, asm, text):
        self.asm = asm
        self.t = tokenize(text)
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        # 2500AD: a leading < or > selects the low/high byte of the whole
        # expression that follows (#>CLIPCOLS+1 is >(CLIPCOLS+1))
        k, s = self.peek()
        if k == 'op' and s in '<>':
            self.take()
            v = self.parse()
            return v & 0xFF if s == '<' else (v >> 8) & 0xFF
        v = self.p_or()
        if self.i != len(self.t):
            raise AsmError('junk in expression at %r' % (self.t[self.i:],))
        return v

    def p_or(self):
        v = self.p_and()
        while True:
            k, s = self.peek()
            if (k == 'op' and s in '^|!') or (k == 'dop' and s.upper() in ('.OR.', '.XOR.')):
                self.take()
                r = self.p_and()
                v = (v ^ r) if (k == 'dop' and s.upper() == '.XOR.') else (v | r)
            else:
                return v

    def p_and(self):
        v = self.p_cmp()
        while True:
            k, s = self.peek()
            if (k == 'op' and s == '&') or (k == 'dop' and s.upper() == '.AND.'):
                self.take()
                v &= self.p_cmp()
            else:
                return v

    def p_cmp(self):
        v = self.p_add()
        while True:
            k, s = self.peek()
            if k == 'op' and s in ('=', '<>', '<', '>', '<=', '>='):
                self.take()
                r = self.p_add()
                v = {'=': v == r, '<>': v != r, '<': v < r, '>': v > r,
                     '<=': v <= r, '>=': v >= r}[s]
                v = 0xFFFF if v else 0
            elif k == 'dop' and s.upper() in ('.EQ.', '.NE.', '.LT.', '.GT.', '.LE.', '.GE.'):
                self.take()
                r = self.p_add()
                v = {'.EQ.': v == r, '.NE.': v != r, '.LT.': v < r, '.GT.': v > r,
                     '.LE.': v <= r, '.GE.': v >= r}[s.upper()]
                v = 0xFFFF if v else 0
            else:
                return v

    def p_add(self):
        v = self.p_mul()
        while True:
            k, s = self.peek()
            if k == 'op' and s in '+-':
                self.take()
                r = self.p_mul()
                v = v + r if s == '+' else v - r
            else:
                return v

    def p_mul(self):
        v = self.p_un()
        while True:
            k, s = self.peek()
            if k == 'op' and s in '*/':
                self.take()
                r = self.p_un()
                if s == '*':
                    v = v * r
                else:
                    v = v // r if r else 0
            elif k == 'dop' and s.upper() in ('.MOD.', '.SHL.', '.SHR.'):
                self.take()
                r = self.p_un()
                u = s.upper()
                if u == '.MOD.':
                    v = v % r if r else 0
                elif u == '.SHL.':
                    v = v << r
                else:
                    v = v >> r
            else:
                return v

    def p_un(self):
        k, s = self.peek()
        if k == 'op' and s == '-':
            self.take()
            return -self.p_un()
        if k == 'op' and s == '+':
            self.take()
            return self.p_un()
        if k == 'op' and s in ('\\', '~'):
            self.take()
            return ~self.p_un() & 0xFFFF
        if k == 'op' and s == '<':
            self.take()
            return self.p_un() & 0xFF
        if k == 'op' and s == '>':
            self.take()
            return (self.p_un() >> 8) & 0xFF
        if k == 'dop' and s.upper() in ('.LOW.', '.HIGH.', '.NOT.'):
            self.take()
            v = self.p_un()
            return {'.LOW.': v & 0xFF, '.HIGH.': (v >> 8) & 0xFF, '.NOT.': ~v & 0xFFFF}[s.upper()]
        return self.p_atom()

    def p_atom(self):
        k, s = self.take()
        if k == 'hex':
            return int(s[1:], 16)
        if k == 'bin':
            return int(s[1:], 2)
        if k == 'dec':
            return int(s, 10)
        if k == 'chr':
            body = s[1:-1].replace(s[0] * 2, s[0])
            v = 0
            for c in body.encode('latin1'):
                v = (v << 8) | c
            return v
        if k == 'op' and s == '(':
            v = self.p_or()
            k2, s2 = self.take()
            if s2 != ')':
                raise AsmError('missing )')
            return v
        if k == 'op' and s == '*':
            return self.asm.pc
        if k == 'id':
            if s == '$':
                return self.asm.pc
            return self.asm.lookup(s)
        if k == 'pc':
            return self.asm.pc
        raise AsmError('unexpected %r in expression' % (s,))


def split_args(s):
    """Split on commas not inside quotes/parens."""
    out, cur, depth, q = [], '', 0, None
    for c in s:
        if q:
            cur += c
            if c == q:
                q = None
        elif c in '"\'':
            q = c
            cur += c
        elif c == '(':
            depth += 1
            cur += c
        elif c == ')':
            depth -= 1
            cur += c
        elif c == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += c
    if cur.strip() or out:
        out.append(cur.strip())
    return out


def strip_comment(s):
    q = None
    for i, c in enumerate(s):
        if q:
            if c == q:
                q = None
        elif c in '"\'':
            # an apostrophe directly after an identifier char is not a quote
            if c == "'" and i and (s[i - 1].isalnum()):
                continue
            q = c
        elif c == ';':
            return s[:i]
    return s


# --------------------------------------------------------------------------
# assembler
# --------------------------------------------------------------------------
class Macro:
    def __init__(self, name, params, body):
        self.name = name
        self.params = params
        self.body = body


class Asm:
    def __init__(self, incdirs, kitdir, defines):
        self.incdirs = incdirs
        self.kitdir = kitdir
        self.defines = defines
        self.syms = {}
        self.prev = {}
        self.sizes = {}        # (file, line, expansion-id) -> chosen size
        self.files = {}

    # ---- symbols ----
    def mangle(self, name):
        if name[:1] == '?':
            return '%s~%d' % (name, self.scope)
        return name

    def lookup(self, name):
        name = self.mangle(name)
        if name in self.syms:
            return self.syms[name]
        if name in self.prev:
            self.unresolved += 1
            return self.prev[name]
        self.undef.add(name)
        raise Undefined(name)

    def define(self, name, val, where, label=False):
        if label and name[:1] != '?':
            self.scope += 1
        name = self.mangle(name)
        if name in self.syms and self.syms[name] != val:
            self.err('symbol %s redefined (%04X -> %04X)' % (name, self.syms[name], val), where)
        self.syms[name] = val
        self.defpass.add(name)

    def ev(self, text, default=0):
        try:
            return Expr(self, text).parse()
        except Undefined:
            if self.final:
                raise AsmError('undefined symbol(s): %s' % ' '.join(sorted(self.undef)))
            return default

    def ev_known(self, text):
        """Evaluate; return None if anything is undefined at this point."""
        try:
            saved = self.unresolved
            v = Expr(self, text).parse()
            return v, self.unresolved == saved
        except Undefined:
            return None, False

    # ---- files ----
    def find_file(self, name, cur_dir):
        n = name.strip().strip('"')
        n2 = re.sub(r'^[A-Za-z]:', '', n).replace('\\', '/')
        cands = []
        if re.match(r'(?i)^/PR/LYNX/INCLUDE/', n2):
            cands.append((self.kitdir, n2.split('/')[-1]))
        else:
            for d in self.incdirs + [cur_dir]:
                cands.append((d, n2))
        for d, rel in cands:
            p = self._ci_path(d, rel)
            if p:
                return p
        raise AsmError('cannot find include file %s' % name)

    @staticmethod
    def _ci_path(base, rel):
        cur = base
        for part in [p for p in rel.split('/') if p]:
            if part == '..':
                cur = os.path.dirname(os.path.abspath(cur))
                continue
            if not os.path.isdir(cur):
                return None
            hit = None
            for e in os.listdir(cur):
                if e.upper() == part.upper():
                    hit = e
                    break
            if hit is None:
                return None
            cur = os.path.join(cur, hit)
        return cur if os.path.isfile(cur) else None

    def read_lines(self, path):
        if path not in self.files:
            with open(path, 'rb') as f:
                txt = f.read().decode('latin1')
            txt = txt.replace('\r', '').split('\x1a')[0]
            self.files[path] = txt.split('\n')
        return self.files[path]

    # ---- output ----
    def emit(self, bs):
        if self.sect_ref:
            self.pc += len(bs)
            return
        for b in bs:
            if self.final:
                if self.pc in self.mem and self.mem[self.pc] != (b & 0xFF):
                    raise AsmError('overlapping output at $%04X' % self.pc)
                self.mem[self.pc] = b & 0xFF
            self.pc += 1

    def err(self, msg, where):
        e = AsmError('%s:%d: %s' % (os.path.basename(where[0]), where[1], msg))
        e.located = True
        raise e

    # ---- driver ----
    def assemble(self, path, maxpass=12):
        last = None
        for p in range(maxpass):
            self.final = False
            self.run(path)
            snap = dict(self.syms)
            if p > 0 and snap == last and self.unresolved == 0 and not self.undef:
                break
            last = snap
            self.prev = snap
        self.final = True
        self.run(path)
        if self.syms != last:
            raise AsmError('symbols did not converge')
        return self.mem

    def reset(self):
        """Clear all per-pass state."""
        self.syms = dict(self.defines)
        self.defpass = set()
        self.scope = 0
        self.undef = set()
        self.unresolved = 0
        self.macros = {}
        self.mem = {}
        self.pc = 0
        self.sect_ref = False
        self.section_pcs = {}
        self.section_ref = {}
        self.cur_section = None
        self.expcount = 0

    def run(self, path):
        self.reset()
        self.process_file(path)

    def process_file(self, path):
        lines = self.read_lines(path)
        self.process_lines([(path, i + 1, l) for i, l in enumerate(lines)], None)

    def process_lines(self, lines, mctx):
        # conditional stack entries: [active, taken, parent_active]
        cond = []
        i = 0
        n = len(lines)
        while i < n:
            path, ln, raw = lines[i]
            where = (path, ln)
            i += 1
            line = raw
            if mctx is not None:
                line = self.subst(line, mctx)
            if line[:1] == '*' or line.lstrip()[:1] == ';':
                continue
            body = strip_comment(line).rstrip()
            if not body.strip():
                continue
            label, op, operand = self.split_fields(body)
            uop = op.upper() if op else ''
            active = all(c[0] for c in cond)

            # conditionals
            if uop in ('IF', 'IFMA', 'IFDEF', 'IFNDEF', 'IFE', 'IFN'):
                if not active:
                    cond.append([False, True])
                    continue
                if uop == 'IFMA':
                    k = self.ev(operand)
                    v = mctx is not None and k <= len(mctx['args']) and mctx['args'][k - 1] != ''
                elif uop == 'IFDEF':
                    v = operand.strip() in self.syms or operand.strip() in self.prev
                elif uop == 'IFNDEF':
                    v = not (operand.strip() in self.syms or operand.strip() in self.prev)
                else:
                    v = self.ev(operand) != 0
                cond.append([bool(v), bool(v)])
                continue
            if uop == 'ELSE':
                if not cond:
                    self.err('ELSE without IF', where)
                c = cond[-1]
                c[0] = not c[1]
                c[1] = True
                continue
            if uop == 'ENDIF':
                if not cond:
                    self.err('ENDIF without IF', where)
                cond.pop()
                continue
            if not active:
                if uop == 'MACRO':
                    # skip the whole definition
                    while i < n and self.split_fields(strip_comment(lines[i][2]))[1].upper() != 'ENDM':
                        i += 1
                    i += 1
                continue

            if uop == 'MACRO':
                body_lines = []
                depth = 0
                while i < n:
                    l2 = lines[i]
                    f = self.split_fields(strip_comment(l2[2]))[1].upper()
                    i += 1
                    if f == 'MACRO':
                        depth += 1
                    if f == 'ENDM':
                        if depth == 0:
                            break
                        depth -= 1
                    body_lines.append(l2)
                params = [p.strip() for p in split_args(operand)] if operand.strip() else []
                self.macros[label.upper()] = Macro(label, params, body_lines)
                continue
            if uop == 'ENDM':
                continue

            try:
                self.statement(label, op, uop, operand, where, mctx)
            except AsmError as e:
                if not getattr(e, 'located', False):
                    e2 = AsmError('%s:%d: %s' % (os.path.basename(path), ln, e))
                    e2.located = True
                    raise e2
                raise
            if uop == 'END':
                return
        if cond:
            self.err('unterminated IF', lines[-1][:2])

    def split_fields(self, body):
        if not body.strip():
            return '', '', ''
        if body[:1] not in ' \t':
            m = re.match(r'(\S+)\s*(.*)$', body)
            label = m.group(1)
            rest = m.group(2)
            if label.endswith(':'):
                label = label[:-1]
        else:
            label = ''
            rest = body.strip()
        m = re.match(r'(\S+)\s*(.*)$', rest)
        if not m:
            return label, '', ''
        op = m.group(1)
        operand = m.group(2).strip()
        # "LABEL EQU x" written as "LABEL = x"
        return label, op, operand

    def subst(self, line, mctx):
        params = mctx['params']
        args = mctx['args']
        amap = {}
        for k, p in enumerate(params):
            amap[p.upper()] = args[k] if k < len(args) else ''
        # |PARAM| concatenation
        def rep_bar(m):
            key = m.group(1).upper()
            return amap.get(key, m.group(0))
        line = re.sub(r'\|([A-Za-z_][A-Za-z0-9_]*)\|', rep_bar, line)
        # whole identifiers
        if amap:
            def rep_id(m):
                return amap.get(m.group(0).upper(), m.group(0)) if m.group(0).upper() in amap else m.group(0)
            out = []
            # do not substitute inside comments
            code = strip_comment(line)
            rest = line[len(code):]
            code = re.sub(r'(?<![A-Za-z0-9_@?$%])[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_@?#])', rep_id, code)
            line = code + rest
        # macro-local labels: '#' following an identifier char
        line = re.sub(r'(?<=[A-Za-z0-9_@?.])#', '%04d' % mctx['id'], line)
        return line

    # ---- statements ----
    def statement(self, label, op, uop, operand, where, mctx):
        if uop in ('EQU', '=', 'SET', 'DEFL'):
            if not label:
                self.err('EQU without label', where)
            v = self.ev(operand)
            if uop in ('SET', 'DEFL'):
                self.syms[label] = v
            else:
                self.define(label, v & 0xFFFFFFFF if v >= 0 else v & 0xFFFF, where)
            return
        if label and uop not in ('MACRO',):
            if uop == 'SECTION':
                pass
            else:
                self.define(label, self.pc, where, label=True)
        if not op:
            return
        if uop in self.macros and uop not in OPS:
            m = self.macros[uop]
            self.expcount += 1
            args = split_args(operand) if operand.strip() else []
            ctx = {'params': m.params, 'args': args, 'id': self.expcount}
            self.process_lines(m.body, ctx)
            return
        if uop in OPS:
            self.instr(uop, operand, where)
            return
        d = uop.lstrip('.')
        if d in ('BYTE', 'DB', 'FCB', 'DEFB', 'ASCII', 'TEXT', 'FCC'):
            for a in split_args(operand):
                if a[:1] in '"\'' and a[-1:] == a[:1] and len(a) >= 2:
                    body = a[1:-1].replace(a[0] * 2, a[0])
                    self.emit(list(body.encode('latin1')))
                else:
                    self.emit([self.ev(a) & 0xFF])
            return
        if d in ('WORD', 'DW', 'FDB', 'DEFW'):
            for a in split_args(operand):
                v = self.ev(a)
                self.emit([v & 0xFF, (v >> 8) & 0xFF])
            return
        if d in ('LONG', 'DL'):
            for a in split_args(operand):
                v = self.ev(a)
                self.emit([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])
            return
        if d in ('DS', 'RMB', 'DEFS'):
            v = self.ev(operand)
            self.reserve(v)
            return
        if d in ('BLKB', 'BLKW', 'BLKL'):
            a = split_args(operand)
            cnt = self.ev(a[0])
            fill = self.ev(a[1]) if len(a) > 1 else 0
            w = {'BLKB': 1, 'BLKW': 2, 'BLKL': 4}[d]
            if self.sect_ref:
                self.pc += cnt * w
            else:
                for _ in range(cnt):
                    self.emit([(fill >> (8 * k)) & 0xFF for k in range(w)])
            return
        if d == 'ORG':
            self.pc = self.ev(operand) & 0xFFFF
            return
        if d == 'INCLUDE':
            p = self.find_file(operand, os.path.dirname(os.path.abspath(where[0])))
            self.process_file(p)
            return
        if d == 'SECTION':
            self.section_pcs[self.cur_section] = self.pc
            self.cur_section = label.upper()
            if self.cur_section not in self.section_ref:
                self.section_ref[self.cur_section] = 'REF_ONLY' in operand.upper()
            self.sect_ref = self.section_ref[self.cur_section]
            self.pc = self.section_pcs.get(self.cur_section, 0)
            return
        if d == 'ENDS':
            self.section_pcs[self.cur_section] = self.pc
            self.cur_section = None
            self.sect_ref = False
            return
        if d == 'CODE':
            self.section_pcs[self.cur_section] = self.pc
            self.cur_section = 'CODE'
            self.sect_ref = False
            self.pc = self.section_pcs.get('CODE', 0)
            return
        if d in ('ABSOLUTE', 'RELATIVE', 'LIST', 'GLOBALS', 'SYMBOLS', 'CHIP', 'NOLIST',
                 'PAGE', 'TITLE', 'SUBTTL', 'EJECT', 'END', 'NAME', 'GLOBAL', 'PUBLIC',
                 'EXTERN', 'EXTERNAL', 'XREF', 'XDEF'):
            return
        self.err('unknown opcode/directive %s' % op, where)

    def reserve(self, v):
        if self.sect_ref:
            self.pc += v
        else:
            self.emit([0] * v)

    def instr(self, m, operand, where):
        modes = OPS[m]
        o = operand.strip()
        if not o or o.upper() == 'A':
            if 'imp' in modes:
                self.emit([modes['imp']])
                return
            if 'acc' in modes:
                self.emit([modes['acc']])
                return
            self.err('%s needs an operand' % m, where)
        if 'rel' in modes:
            tgt = self.ev(o, self.pc)
            off = tgt - (self.pc + 2)
            if self.final and not -128 <= off <= 127:
                self.err('branch out of range (%d)' % off, where)
            self.emit([modes['rel'], off & 0xFF])
            return
        if o[0] == '#':
            v = self.ev(o[1:])
            self.emit([modes['imm'], v & 0xFF])
            return
        u = o.upper().replace(' ', '')
        mode = None
        expr = o
        mm = re.match(r'^\((.*)\)\s*,\s*[Yy]$', o)
        if mm:
            mode, expr = 'izy', mm.group(1)
        else:
            mm = re.match(r'^\((.*),\s*[Xx]\s*\)$', o)
            if mm:
                mode, expr = ('aix' if m == 'JMP' else 'izx'), mm.group(1)
            else:
                mm = re.match(r'^\((.*)\)$', o)
                if mm and self._balanced(mm.group(1)):
                    mode, expr = ('ind' if m == 'JMP' else 'izp'), mm.group(1)
        if mode is None:
            mm = re.match(r'^(.*),\s*([XxYy])$', o)
            if mm:
                expr = mm.group(1)
                mode = 'abx' if mm.group(2).upper() == 'X' else 'aby'
            else:
                mode = 'abs'
        key = (where, self.cur_macro_id())
        if mode in ZPFORM:
            zpm = ZPFORM[mode]
            if key in self.sizes:
                usezp = self.sizes[key]
            else:
                v, known = self.ev_known(expr)
                usezp = known and v is not None and 0 <= v < 0x100 and zpm in modes
                if zpm not in modes:
                    usezp = False
                self.sizes[key] = usezp
            if mode not in modes and zpm in modes:
                usezp = True
            if usezp:
                v = self.ev(expr)
                self.emit([modes[zpm], v & 0xFF])
                return
            if mode not in modes:
                self.err('bad addressing mode for %s' % m, where)
            v = self.ev(expr)
            self.emit([modes[mode], v & 0xFF, (v >> 8) & 0xFF])
            return
        if mode not in modes:
            self.err('bad addressing mode for %s: %s' % (m, o), where)
        v = self.ev(expr)
        if mode in ('izx', 'izy', 'izp'):
            self.emit([modes[mode], v & 0xFF])
        else:
            self.emit([modes[mode], v & 0xFF, (v >> 8) & 0xFF])

    def cur_macro_id(self):
        return self.expcount

    @staticmethod
    def _balanced(s):
        d = 0
        for c in s:
            if c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d < 0:
                    return False
        return d == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('-I', dest='inc', action='append', default=[])
    ap.add_argument('-k', '--kit', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kit'))
    ap.add_argument('--sym')
    ap.add_argument('-D', dest='defs', action='append', default=[])
    a = ap.parse_args()
    defs = {}
    for d in a.defs:
        k, _, v = d.partition('=')
        defs[k] = int(v, 0) if v else 1
    asm = Asm(a.inc, a.kit, defs)
    try:
        mem = asm.assemble(a.src)
    except AsmError as e:
        print('a65: error: %s' % e, file=sys.stderr)
        sys.exit(1)
    if not mem:
        print('a65: error: no code emitted', file=sys.stderr)
        sys.exit(1)
    lo, hi = min(mem), max(mem)
    data = bytes(mem.get(x, 0) for x in range(lo, hi + 1))
    with open(a.out, 'wb') as f:
        f.write(data)
    if a.sym:
        with open(a.sym, 'w') as f:
            for k in sorted((k for k in asm.syms if '~' not in k), key=lambda s: s.upper()):
                f.write('%-24s EQU $%04X\n' % (k, asm.syms[k] & 0xFFFF))


if __name__ == '__main__':
    main()
