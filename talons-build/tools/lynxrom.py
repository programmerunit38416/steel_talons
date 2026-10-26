#!/usr/bin/env python3
"""
lynxrom.py LAYOUT.HSF OUT.ROM [-k kitdir]

Replacement for the Atari LYNXROM tool.  Reads a HandyROM layout file:

    FILE  n        start directory entry n (number or symbol)
    BIN   name     file in BIN format (01 addr / 12 len data / 03 run / 00)
    RAW   name     raw file
    ALIGN n        align the next file to an n-byte boundary

and writes a ROMSIZE image: ROM_HEADER_SIZE bytes reserved for the encrypted
boot header, then the directory (8 bytes per entry: page, offset, flag, dest,
size), then the files packed in layout order.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a65  # noqa: E402


def read_bin(path):
    d = open(path, 'rb').read()
    i, dest, out = 0, None, bytearray()
    while i < len(d):
        t = d[i]
        if t == 0x01:
            dest = d[i + 1] | d[i + 2] << 8
            i += 3
        elif t == 0x12:
            n = d[i + 1] | d[i + 2] << 8
            out += d[i + 3:i + 3 + n]
            i += 3 + n
        elif t == 0x03:
            i += 3
        elif t == 0x00:
            break
        else:
            raise SystemExit('lynxrom: %s: bad BIN record $%02X at %d' % (path, t, i))
    return dest or 0, bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hsf')
    ap.add_argument('out')
    ap.add_argument('-I', dest='inc', action='append', default=[],
                    help='directories searched for files before the layout directory')
    ap.add_argument('-k', '--kit', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kit'))
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.hsf))

    # the layout's INCLUDEs (CART.I, CARTDEFS.INC) supply the ROM geometry
    asm = a65.Asm([], a.kit, {})
    asm.reset()
    asm.final = True
    asm.sect_ref = True
    lines = asm.read_lines(a.hsf)
    entries = []
    cur = None
    for ln, raw in enumerate(lines, 1):
        if raw[:1] == '*' or raw.lstrip()[:1] == ';':
            continue
        body = a65.strip_comment(raw).strip()
        if not body:
            continue
        parts = body.split(None, 1)
        op = parts[0].upper()
        arg = parts[1].strip() if len(parts) > 1 else ''
        if op == 'INCLUDE':
            asm.process_file(asm.find_file(arg, base))
        elif op == 'FILE':
            cur = {'num': asm.ev(arg), 'align': 1, 'items': []}
            entries.append(cur)
        elif op == 'ALIGN':
            cur['align'] = asm.ev(arg)
        elif op in ('BIN', 'RAW'):
            p = None
            for d in a.inc + [base]:
                p = p or asm._ci_path(d, arg.replace('\\', '/'))
            if not p:
                raise SystemExit('lynxrom: %s:%d: cannot find %s' % (a.hsf, ln, arg))
            if op == 'BIN':
                dest, data = read_bin(p)
            else:
                dest, data = 0, open(p, 'rb').read()
            cur['items'].append((dest, data))
        else:
            raise SystemExit('lynxrom: %s:%d: unknown directive %s' % (a.hsf, ln, op))

    S = asm.syms
    romsize = S['ROMSIZE']
    pagesize = romsize // S['ROMPAGECOUNT']
    hdr = S['ROM_HEADER_SIZE']
    nent = max(e['num'] for e in entries) + 1
    rom = bytearray(romsize)
    pos = hdr + nent * S['ROMDIR_ENTRY_SIZE']
    for e in entries:
        if pos % e['align']:
            pos += e['align'] - pos % e['align']
        dest = e['items'][0][0] if e['items'] else 0
        data = b''.join(d for _, d in e['items'])
        if pos + len(data) > romsize:
            raise SystemExit('lynxrom: ROM overflow at file %d' % e['num'])
        struct.pack_into('<BHBHH', rom, hdr + 8 * e['num'], pos // pagesize, pos % pagesize,
                         0, dest, len(data))
        rom[pos:pos + len(data)] = data
        pos += len(data)
    open(a.out, 'wb').write(rom)
    print('lynxrom: %d files, %d of %d bytes used (%d free)' % (len(entries), pos, romsize, romsize - pos))


if __name__ == '__main__':
    main()
