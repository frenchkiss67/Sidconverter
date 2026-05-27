"""6510 player byte-level checks (no emulator, just static analysis)."""
from __future__ import annotations

from sidconverter.player import (
    IMAGE_END,
    INIT_ADDR,
    TABLE_BASE,
    TABLE_STRIDE,
    VOICE_REGS,
    WAVEFORMS,
    build_payload,
    make_init,
    make_play,
)


def test_init_size_stable_for_each_waveform():
    sizes = {wf: len(make_init(waveform=v, ad=0, sr=0xF0)) for wf, v in WAVEFORMS.items()}
    # Pulse pulls in 6 extra STAs for the PW registers (2 LDA + 6 STAs)
    assert sizes["pulse"] > sizes["triangle"]
    assert sizes["triangle"] == sizes["sawtooth"] == sizes["noise"]


def test_init_ends_with_rts():
    code = make_init(waveform=WAVEFORMS["triangle"], ad=0, sr=0xF0)
    assert code[-1] == 0x60


def test_play_size_within_branch_range():
    """BNE / BCC operands are signed bytes; the body must stay within ±127."""
    for n in (1, 50, 200, 255):
        code = make_play(waveform=WAVEFORMS["triangle"], num_notes=n)
        # Find BNE and BCC operands and check they decode to a valid offset
        # whose target stays inside the body.
        assert code[0] == 0xC6  # DEC $FB
        assert code[2] == 0xD0  # BNE
        bne_offset = code[3]
        # signed
        if bne_offset > 127:
            bne_offset -= 256
        target = 4 + bne_offset
        assert 0 <= target < len(code)
        assert code[target] == 0x60  # lands on RTS


def test_play_retriggers_all_three_voices():
    code = make_play(waveform=WAVEFORMS["triangle"], num_notes=4)
    # Each voice's gate-on store should appear once
    for v in VOICE_REGS:
        ctrl_addr = 0xD400 + v["ctrl"]
        sta_seq = bytes([0x8D, ctrl_addr & 0xFF, (ctrl_addr >> 8) & 0xFF])
        # Gate off (waveform & ~1) and gate on (waveform | 1) both write to ctrl
        assert code.count(sta_seq) == 2


def test_build_payload_image_size():
    cols = [[0x1234] * 5, [0] * 5, [0] * 5]
    durs = [10] * 5
    data, play_addr = build_payload(
        cols, durs, waveform=WAVEFORMS["triangle"], ad=0x00, sr=0xF0
    )
    # 2 bytes embedded load address + the image
    assert len(data) == 2 + (IMAGE_END - INIT_ADDR)
    assert play_addr > INIT_ADDR


def test_build_payload_writes_freq_tables_at_right_offsets():
    cols = [
        [0xABCD, 0x1234],
        [0xBEEF, 0xCAFE],
        [0xDEAD, 0xBABE],
    ]
    data, _ = build_payload(
        cols, [10, 20], waveform=WAVEFORMS["pulse"], ad=0x00, sr=0xF0
    )
    image = data[2:]   # skip embedded load address
    for v, col in enumerate(cols):
        lo_off = (TABLE_BASE - INIT_ADDR) + (2 * v) * TABLE_STRIDE
        hi_off = (TABLE_BASE - INIT_ADDR) + (2 * v + 1) * TABLE_STRIDE
        for i, val in enumerate(col):
            assert image[lo_off + i] == val & 0xFF
            assert image[hi_off + i] == (val >> 8) & 0xFF


def test_build_payload_pads_short_columns_with_zero():
    cols = [[0x1234], [], [0xABCD]]
    data, _ = build_payload(cols, [50], waveform=WAVEFORMS["triangle"], ad=0, sr=0xF0)
    image = data[2:]
    # Voice 2 column was empty -> first entry should be 0
    v2_lo_off = (TABLE_BASE - INIT_ADDR) + 2 * TABLE_STRIDE
    assert image[v2_lo_off] == 0


def test_durations_clamp_to_at_least_one():
    cols = [[0x1234], [0], [0]]
    data, _ = build_payload(cols, [0], waveform=WAVEFORMS["triangle"], ad=0, sr=0xF0)
    image = data[2:]
    dur_off = (TABLE_BASE - INIT_ADDR) + 6 * TABLE_STRIDE
    assert image[dur_off] == 1
