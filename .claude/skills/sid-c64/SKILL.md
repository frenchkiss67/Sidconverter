---
name: sid-c64
description: Work with Commodore 64 SID music files. Parse PSID/RSID headers and metadata, render .sid to WAV/MP3 via sidplayfp, convert between PSID and RSID formats, and synthesize a basic .sid from an input audio file using pitch detection. Trigger when the user mentions .sid files, PSID, RSID, SID chip, Commodore 64 music, HVSC, sidplayfp, or asks to convert audio to/from SID.
---

# SID (Commodore 64) skill

This skill provides tools to inspect, render, convert and (best-effort) generate
Commodore 64 SID music files. All scripts live in `scripts/` next to this file.

## File format quick reference

A `.sid` file begins with a PSID or RSID header (big-endian fields):

```
0x00  4  magic        "PSID" or "RSID"
0x04  2  version      1, 2, 3 or 4
0x06  2  dataOffset   0x76 (v1) or 0x7C (v2+)
0x08  2  loadAddress  0 = embedded as first 2 bytes of data
0x0A  2  initAddress
0x0C  2  playAddress
0x0E  2  songs        1..256
0x10  2  startSong    1..songs
0x12  4  speed        bitfield, song N uses bit N-1
0x16  32 name         null-terminated CP1252-ish ASCII
0x36  32 author
0x56  32 released     (was "copyright" in v1 spec)
0x76  2  flags        (v2+)  see below
0x78  1  startPage    (v2+)
0x79  1  pageLength   (v2+)
0x7A  1  secondSIDAddr(v3+)
0x7B  1  thirdSIDAddr (v4+)
```

Flags (v2+): bit 0 = MUS data, bit 1 = PlaySID samples (PSID) or C64 BASIC
(RSID), bits 2-3 = clock (0 unknown, 1 PAL, 2 NTSC, 3 both), bits 4-5 = SID
model (0 unknown, 1 6581, 2 8580, 3 both), bits 6-7 / 8-9 = second/third SID
model.

After the header comes the load address (2 bytes, little-endian) if
`loadAddress == 0`, then the 6510 machine code.

## Usage patterns

### Inspect a SID file

```
python3 scripts/sid_info.py path/to/tune.sid
python3 scripts/sid_info.py path/to/tune.sid --json
```

Prints magic, version, addresses, song count, name/author/released, flags
(clock + SID model + extra SID addresses), and both MD5 hashes used by the
HVSC Songlengths database (`md5 (old)` = libsidplayfp `createMD5` over
data+addresses+speed; `md5 (new)` = MD5 of the file as-is).

### Render SID → WAV / MP3

Wraps `sidplayfp` (preferred) or `sidplay2` if available. Requires the binary
to be installed on the host. Falls back with a clear error otherwise.

```
python3 scripts/sid_to_wav.py tune.sid -o tune.wav            # default song, 3 min
python3 scripts/sid_to_wav.py tune.sid -o tune.wav -t 120     # 120 seconds
python3 scripts/sid_to_wav.py tune.sid -o tune.wav -s 2       # song #2
python3 scripts/sid_to_wav.py tune.sid -o tune.mp3            # auto-pipes to ffmpeg
python3 scripts/sid_to_wav.py tune.sid -o tune.wav -m n -f 44100  # force 8580, 44.1 kHz
```

Extra knobs (passed through to sidplayfp): `-f SR` sample rate, `-m {o,n}`
SID model (o=6581, n=8580; append `f` to disable the filter), `-b POS`
start position `[mins:]secs[.ms]`.

If `sidplayfp` is missing the script prints the apt/brew commands to install
it (`sudo apt install sidplayfp` on Debian/Ubuntu, `brew install sidplayfp`
on macOS).

### Convert PSID ↔ RSID

```
python3 scripts/sid_format_convert.py in.sid -o out.sid --to RSID
python3 scripts/sid_format_convert.py in.sid -o out.sid --to PSID
```

This rewrites the 4-byte magic and clears/sets the PSID-specific "samples"
flag (bit 1). It does **not** rewrite the 6510 code — converting PSID code
that depends on the kernal to RSID will not always produce a playable file.
The script warns when the conversion is unlikely to be safe (e.g. PSID with
`playAddress != 0` or non-zero `loadAddress` going to RSID).

### Audio → SID (best effort)

```
python3 scripts/audio_to_sid.py input.wav -o melody.sid \
    --name "My Tune" --author "Me" --released "2026"

# Tweak voicing, timbre, envelope and target clock:
python3 scripts/audio_to_sid.py input.wav -o melody.sid \
    --voices 3 --waveform sawtooth --adsr 4,8,12,6 --clock ntsc --model 8580
```

Pitch detection runs on the audio (via `librosa.pyin` when available, else
an autocorrelation fallback on the stdlib). The script emits a PSID v2 file
with an embedded 6510 player that steps three SID voices in lockstep:

- `--voices 1` — only voice 1 plays the detected melody.
- `--voices 3` (default) — voice 1 plays the melody, voice 2 plays it one
  octave below (bass), voice 3 plays it a perfect fifth above (sweetener).

Other knobs: `--waveform {triangle,sawtooth,pulse,noise}`, `--adsr A,D,S,R`
(each value 0..15), `--clock {pal,ntsc}`, `--model {6581,8580}`.

The result is still a single-pitch transcription — full polyphonic
transcription would need a much heavier model. Be honest about this when
presenting the output to the user.

### Validate against the format spec

```
python3 scripts/sid_validate.py path/to/tune.sid           # exit 0/2
python3 scripts/sid_validate.py path/to/tune.sid --strict  # warnings -> exit 1
```

Reports spec violations as errors (version range, songs/startSong range,
RSID rules, secondary/third SID address validity) and style/portability
issues as warnings (empty name/author, MUS data flag, v1 header with v2
fields populated).

## Decision guide

- User asks "what's in this .sid?" / "who wrote this tune?" → `sid_info.py`.
- User asks to play, listen, render, export, convert to wav/mp3/ogg → `sid_to_wav.py`.
- User wants to flip the magic between PSID and RSID → `sid_format_convert.py`.
- User wants to turn a hummed melody / wav / mp3 into a .sid → `audio_to_sid.py`,
  default to `--voices 3` for fuller sound; warn that pitch detection is monophonic.
- User asks "is this .sid valid?" / wants to lint a tune before publishing →
  `sid_validate.py`.
- User asks about a SID hash for HVSC Songlengths.md5 → `sid_info.py` prints
  both MD5 variants used by libsidplayfp: `md5 (old)` for legacy entries
  (createMD5: data + init/play/songs little-endian + per-song speed byte +
  optional NTSC 0x02 byte) and `md5 (new)` (MD5 of the file as written, used
  by current HVSC releases).

## Dependencies

- Python 3.8+ (stdlib only for parsing and PSID/RSID conversion).
- `sidplayfp` on PATH for SID → audio rendering.
- `ffmpeg` on PATH for MP3/OGG/M4A output (WAV works without it).
- Optional: `librosa` + `numpy` for higher-quality pitch detection in
  `audio_to_sid.py`. Without them the script falls back to a pure-Python
  autocorrelation pitch tracker that only handles 16-bit PCM WAV input.

When a dependency is missing, the scripts exit with a non-zero status and a
single-line install hint — do not silently produce a corrupt file.
