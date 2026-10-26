#!/usr/bin/env python3
"""
boottest.py STEELTALONS.lyx TALONS.BIN

Runs the second stage boot loader on a 65C02 model (py65) with a model of
the Lynx cart address logic (page shift register clocked by SYSCTL1, data
from IODAT bit 1, byte counter reset by the strobe, as in Handy's CCart),
starting from the state the cc65 first stage leaves: loader copied to
$FB68 and the cart stream at offset 52+151.  Checks that the main program
ends up in RAM at its load address and that the loader jumps to it.
"""
import struct
import sys

from py65.devices.mpu65c02 import MPU
from py65.memory import ObservableMemory

rom = open(sys.argv[1], 'rb').read()
prog = open(sys.argv[2], 'rb').read()
PAGESIZE = 1024
RCART0, IODAT, SYSCTL1 = 0xFCB2, 0xFD8B, 0xFD87


class Cart:
    shifter = 0
    counter = 52 + 151
    strobe = False
    data = 0


c = Cart()
mem = ObservableMemory()


def rd_cart(addr):
    v = rom[c.shifter * PAGESIZE + c.counter]
    if not c.strobe:
        c.counter = (c.counter + 1) % PAGESIZE
    return v


def wr_iodat(addr, v):
    c.data = (v >> 1) & 1


def wr_sysctl1(addr, v):
    s = bool(v & 1)
    if s:
        c.counter = 0
    if c.strobe and not s:
        c.shifter = ((c.shifter << 1) | c.data) & 0xFF
    c.strobe = s


mem.subscribe_to_read([RCART0], rd_cart)
mem.subscribe_to_write([IODAT], wr_iodat)
mem.subscribe_to_write([SYSCTL1], wr_sysctl1)
for i, b in enumerate(rom[52:52 + 151]):
    mem[0xFB68 + i] = b

cpu = MPU(memory=mem, pc=0xFB68)
page, off, flag, dest, size = struct.unpack_from('<BHBHH', rom, 0x19A + 8)
steps = 0
while cpu.pc != dest:
    cpu.step()
    steps += 1
    if steps > 5_000_000:
        sys.exit('boottest: loader did not reach $%04X (pc=$%04X)' % (dest, cpu.pc))
body = prog[6:6 + size]
got = bytes(mem[dest + i] for i in range(size))
ok = got == body
print('boottest: loader jumped to $%04X after %d instructions; %d bytes at $%04X %s'
      % (dest, steps, size, dest, 'match TALONS.BIN' if ok else 'DO NOT MATCH'))
sys.exit(0 if ok else 1)
