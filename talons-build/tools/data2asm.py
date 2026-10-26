#!/usr/bin/env python3
"""data2asm.py < IN > OUT  - binary file to DB lines, 8 bytes per line (CRLF)"""
import sys
d = sys.stdin.buffer.read()
lines = ['\tDB\t' + ','.join('$%02X' % b for b in d[i:i + 8]) for i in range(0, len(d), 8)]
sys.stdout.buffer.write(''.join('\r\n' + l for l in lines).encode())
