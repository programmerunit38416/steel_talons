# Steel Talons (Atari Lynx, 1992) — modern build

This folder builds the Steel Talons Lynx source in `../finalsrc` on a modern
machine with nothing but Python 3. The original DOS toolchain was the 2500AD
X6502/XLINK assembler, Atari's XASM/DATA2ASM/SYM2EQU/LYNXROM tools and the
Lynx dev-kit library in `\PR\LYNX\INCLUDE`. None of those came with the
source, so this folder replaces them.

```
python3 build.py            # build everything into build/
python3 build.py --verify   # ...and compare every output with the shipped files
```

The build takes about 30 seconds. With `--verify`, all 59 outputs
(TALONS.BIN, the 7 overlays, all data and sprite BINs, COMPLETE.ASM and the
256 KB TALONS.ROM) are byte-identical to the prebuilt files from 1992.

## Outputs (`build/`)

| File | What it is |
|---|---|
| `TALONS.ROM` | Cart image exactly as the 1992 build made it. The first 410 bytes are blank: Atari added the encrypted boot block at mastering, so this file does not boot as is. |
| `STEELTALONS.lyx` | TALONS.ROM with a boot loader in those 410 bytes |
| `STEELTALONS.lnx` | The same with a 64-byte LNX header, for emulators (Handy, Mednafen, …) |
| `TALONS.EQU` | Symbols of the main program, used by the overlays (old SYM2EQU step) |

## What's here

- `tools/a65.py` — an assembler for the 2500AD dialect these sources use: macros
  with `|PARAM|` pasting and `?LABEL#` locals, `IFMA`, `?` local labels,
  sections, `.MOD.`, and `<`/`>` applying to the whole expression. It picks
  zero-page vs. absolute forms the way the original assembler did.
- `tools/lynxrom.py` — the LYNXROM replacement: reads `TALONS.HSF` and writes
  the ROM directory and file layout.
- `tools/data2asm.py` — the DATA2ASM replacement (COMPLETE.DNL → COMPLETE.ASM).
- `kit/` — the missing `\PR\LYNX\INCLUDE` files, **reconstructed**:
  - `KITEQU.I`: hardware and kit equates. The values come from the shipped
    TALONS.SYM symbol table (`tools/mkkit.py`).
  - `*.MAC`: kit macros (SPRITES, WAITMATH, READFILE, …), rebuilt from the
    code each one generated in the shipped binary.
  - `SYS.SRC`, `SYSDATA.SRC`, `CART.SRC`: interrupt dispatcher and cartridge
    file system, disassembled and commented by hand.
  - `HSFX.SRC`, `HMUSIC.SRC`, `*.VAR`: the Handy sound-effect and music
    drivers. A tracing disassembler (`tools/recover.py`, run by
    `tools/mksnd.py`) recovered them from the binary with symbolic operands,
    so the code can still move if the game changes.

  These files are not Atari's originals. They assemble to exactly the bytes
  the originals produced.
- `POINTS/` — the 3D model and world files (`..\POINTS\*.TSK`, `UNI*.RAW`).
  These were missing from the source archive and were extracted from the
  shipped TALONS.ROM. Every other file in that ROM matched the source
  byte for byte. The tool that made them (`GW`, from `UNI*.TXT`) is missing,
  so they are inputs here, not build products.
- `boot/` — boot loader for the `.lnx`/`.lyx`. `STAGE1.BIN` is the public
  pre-signed 52-byte first stage from cc65 (`libsrc/lynx/bootldr.s`, Karri
  Kaksonen, zlib license). `BOOT2.ASM` is a new second stage that loads
  directory entry 1 (TALONS.BIN) and jumps to it, as the original header did.
  It skips the title picture the original header showed while loading.
  `tools/boottest.py` runs it on a 65C02 model with a cart model and checks
  that the program lands in RAM correctly (needs `pip install py65`).

## Not rebuilt from source

The art pipeline (`ART.MAK`: LCRAFT from `..\ART\*.BBM` Deluxe Paint files) and
the world builder (`GW`) are missing along with their inputs. Their outputs
(`.HCR` sprite sources, `.TSK`/`.RAW` model data) are used as they are.

## Verifying a change

`tools/symdiff.py OLD.EQU NEW.EQU` lists symbols whose addresses moved. It
helps find where a rebuilt binary first differs from a reference.
`tools/dis65.py` is a plain 65C02 disassembler.
