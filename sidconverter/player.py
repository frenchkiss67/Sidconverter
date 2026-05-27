"""6510 player code generation for sidconverter.

The player drives up to 3 SID voices in lockstep: each "step" reads a
duration byte and one (freq_lo, freq_hi) pair per voice from RAM tables,
retriggers the gate, and waits `duration` frames before stepping again.
The note pointer wraps at the end so the tune loops.

Memory map (load address $1000):

    $1000   init   ; entry called once by the PSID driver
    $10??   play   ; entry called every frame
    $1100   voice 1 freq lo (256 bytes)
    $1200   voice 1 freq hi
    $1300   voice 2 freq lo
    $1400   voice 2 freq hi
    $1500   voice 3 freq lo
    $1600   voice 3 freq hi
    $1700   duration table (frames per step, 1..255)
    $1800   end (load image is $1000..$17FF = 2 KiB)

Zero page: $FB = remaining frames for current step, $FC = step index.

Waveform constants:
    TRIANGLE  0x10
    SAWTOOTH  0x20
    PULSE     0x40    (also requires non-zero pulse width per voice)
    NOISE     0x80
"""
from __future__ import annotations

import struct

WAVEFORMS = {
    "triangle": 0x10,
    "sawtooth": 0x20,
    "pulse":    0x40,
    "noise":    0x80,
}

INIT_ADDR = 0x1000
TABLE_BASE = 0x1100
TABLE_STRIDE = 0x0100
NUM_TABLES = 7       # 3 voices × (lo + hi) + durations
IMAGE_END = TABLE_BASE + TABLE_STRIDE * NUM_TABLES

# SID register offsets (relative to $D400) for each voice
VOICE_REGS = [
    {"flo": 0x00, "fhi": 0x01, "pwlo": 0x02, "pwhi": 0x03,
     "ctrl": 0x04, "ad": 0x05, "sr": 0x06},
    {"flo": 0x07, "fhi": 0x08, "pwlo": 0x09, "pwhi": 0x0A,
     "ctrl": 0x0B, "ad": 0x0C, "sr": 0x0D},
    {"flo": 0x0E, "fhi": 0x0F, "pwlo": 0x10, "pwhi": 0x11,
     "ctrl": 0x12, "ad": 0x13, "sr": 0x14},
]


def _lda_imm(v: int) -> bytes:        return bytes([0xA9, v & 0xFF])
def _ldx_imm(v: int) -> bytes:        return bytes([0xA2, v & 0xFF])
def _sta_zp(zp: int) -> bytes:        return bytes([0x85, zp & 0xFF])
def _lda_zp(zp: int) -> bytes:        return bytes([0xA5, zp & 0xFF])
def _ldx_zp(zp: int) -> bytes:        return bytes([0xA6, zp & 0xFF])
def _inc_zp(zp: int) -> bytes:        return bytes([0xE6, zp & 0xFF])
def _dec_zp(zp: int) -> bytes:        return bytes([0xC6, zp & 0xFF])
def _cmp_imm(v: int) -> bytes:        return bytes([0xC9, v & 0xFF])
def _sta_abs(a: int) -> bytes:        return bytes([0x8D, a & 0xFF, (a >> 8) & 0xFF])
def _sta_abs_x(a: int) -> bytes:      return bytes([0x9D, a & 0xFF, (a >> 8) & 0xFF])
def _lda_abs_x(a: int) -> bytes:      return bytes([0xBD, a & 0xFF, (a >> 8) & 0xFF])
def _rts() -> bytes:                  return b"\x60"
def _dex() -> bytes:                  return b"\xCA"
def _bpl(off: int) -> bytes:          return bytes([0x10, off & 0xFF])
def _bne(off: int) -> bytes:          return bytes([0xD0, off & 0xFF])
def _bcc(off: int) -> bytes:          return bytes([0x90, off & 0xFF])


def make_init(*, waveform: int, ad: int, sr: int, pw: int = 0x0800) -> bytes:
    """Emit the 6510 init routine for the chosen waveform + ADSR."""
    out = bytearray()
    # Zero the 25-byte SID register block ($D400..$D418)
    out += _lda_imm(0x00)
    out += _ldx_imm(0x18)
    loop_start = len(out)
    out += _sta_abs_x(0xD400)
    out += _dex()
    # branch back to start of loop
    out += _bpl(loop_start - (len(out) + 2))
    # Max volume, no filter
    out += _lda_imm(0x0F)
    out += _sta_abs(0xD418)
    # AD/SR for every voice
    out += _lda_imm(ad)
    for v in VOICE_REGS:
        out += _sta_abs(0xD400 + v["ad"])
    out += _lda_imm(sr)
    for v in VOICE_REGS:
        out += _sta_abs(0xD400 + v["sr"])
    # Pulse width only matters for the pulse waveform
    if waveform == WAVEFORMS["pulse"]:
        out += _lda_imm(pw & 0xFF)
        for v in VOICE_REGS:
            out += _sta_abs(0xD400 + v["pwlo"])
        out += _lda_imm((pw >> 8) & 0x0F)
        for v in VOICE_REGS:
            out += _sta_abs(0xD400 + v["pwhi"])
    # Counters
    out += _lda_imm(0x01)
    out += _sta_zp(0xFB)
    out += _lda_imm(0x00)
    out += _sta_zp(0xFC)
    out += _rts()
    return bytes(out)


def make_play(*, waveform: int, num_notes: int) -> bytes:
    """Emit the play routine that walks the per-voice note tables."""
    # We build the body without the BNE-to-done offset, then patch it.
    body = bytearray()
    body += _dec_zp(0xFB)
    bne_pos = len(body)
    body += _bne(0)                         # placeholder
    body += _ldx_zp(0xFC)
    # duration
    body += _lda_abs_x(TABLE_BASE + 6 * TABLE_STRIDE)
    body += _sta_zp(0xFB)
    # Each voice
    for i, regs in enumerate(VOICE_REGS):
        body += _lda_abs_x(TABLE_BASE + (2 * i) * TABLE_STRIDE)
        body += _sta_abs(0xD400 + regs["flo"])
        body += _lda_abs_x(TABLE_BASE + (2 * i + 1) * TABLE_STRIDE)
        body += _sta_abs(0xD400 + regs["fhi"])
        body += _lda_imm(waveform & 0xFE)       # gate off
        body += _sta_abs(0xD400 + regs["ctrl"])
        body += _lda_imm(waveform | 0x01)       # gate on
        body += _sta_abs(0xD400 + regs["ctrl"])
    # advance index, wrap at num_notes
    body += _inc_zp(0xFC)
    body += _lda_zp(0xFC)
    body += _cmp_imm(num_notes)
    bcc_pos = len(body)
    body += _bcc(0)                         # placeholder
    body += _lda_imm(0x00)
    body += _sta_zp(0xFC)
    done_pos = len(body)
    body += _rts()

    # Patch BNE / BCC: relative offset = target - (operand_pos + 1).
    # 6510 branch operands are *signed* bytes — if the body ever grows past
    # 127 bytes from the branch, the silent `& 0xFF` would produce wrong
    # code. Assert instead.
    def _patch_branch(operand_pos: int, target_pos: int, mnemonic: str) -> None:
        offset = target_pos - (operand_pos + 1)
        if not -128 <= offset <= 127:
            raise OverflowError(
                f"{mnemonic} branch out of signed-byte range "
                f"({offset:+d}); play routine has outgrown the 8-bit reach. "
                "Refactor the player to use a JMP trampoline."
            )
        body[operand_pos] = offset & 0xFF

    _patch_branch(bne_pos + 1, done_pos, "BNE")
    _patch_branch(bcc_pos + 1, done_pos, "BCC")

    return bytes(body)


def build_payload(
    note_columns: list[list[int]],   # 3 entries, each a list of SID freq registers
    durations: list[int],
    *,
    waveform: int,
    ad: int,
    sr: int,
    pulse_width: int = 0x0800,
) -> tuple[bytes, int]:
    """Return (data bytes for the SID payload, play_address).

    `note_columns` must have exactly 3 entries (one per voice); each
    column may be shorter than the others — missing entries are padded
    with 0 (silent). `durations` is one byte per step.
    """
    assert len(note_columns) == 3
    n = len(durations)
    init = make_init(waveform=waveform, ad=ad, sr=sr, pw=pulse_width)
    play = make_play(waveform=waveform, num_notes=n)
    play_addr = INIT_ADDR + len(init)

    image = bytearray(IMAGE_END - INIT_ADDR)
    image[: len(init)] = init
    image[len(init) : len(init) + len(play)] = play

    for v in range(3):
        col = note_columns[v]
        for i in range(n):
            freq = col[i] if i < len(col) else 0
            image[(TABLE_BASE - INIT_ADDR) + (2 * v) * TABLE_STRIDE + i] = freq & 0xFF
            image[(TABLE_BASE - INIT_ADDR) + (2 * v + 1) * TABLE_STRIDE + i] = (freq >> 8) & 0xFF
    for i in range(n):
        image[(TABLE_BASE - INIT_ADDR) + 6 * TABLE_STRIDE + i] = max(1, durations[i] & 0xFF)

    # The PSID format wants the load address embedded as the first 2 bytes
    # of the data when the header's loadAddress field is zero.
    return struct.pack("<H", INIT_ADDR) + bytes(image), play_addr
