#!/usr/bin/env python3
# Build a DrayBoot-bootable image for the Vigor2860 "Boot DrayOS" / RAM-FW path.
#
# Layout (confirmed against Drayboot boot routine base+0x4874):
#   0x000  word0 (BE) = total image length in bytes
#   0x008  "rDkmfaaryTedecz" signature (15 bytes) - needed for TFTP FW_MODE_BIN
#          detection; ignored by the from-flash boot path (harmless either way)
#   0x100  PAYLOAD  (linked & entered at 0x80020000; <= 0x80000 bytes is executed)
#   end-4  word (BE) = ~(sum of all preceding BE words)   one's-complement checksum
#
# Boot path copies a FIXED 0x80000 (512 KiB) from image+0x100 to 0x80020000 and
# jumps there. Payload MUST be position-linked for 0x80020000 and <= 0x80000.
import sys, struct

SIG = b"rDkmfaaryTedecz"
HDR = 0x100
COPY = 0x80000          # bytes the loader copies+executes
ENTRY = 0x80020000

def build(payload: bytes, add_sig=True) -> bytes:
    if len(payload) > COPY:
        raise SystemExit("payload 0x%X > 0x%X (512KiB) - won't fit the fixed copy"
                         % (len(payload), COPY))
    if len(payload) % 4:
        payload += b"\x00" * (4 - len(payload) % 4)
    total = HDR + len(payload) + 4
    buf = bytearray(total)
    struct.pack_into(">I", buf, 0, total)
    if add_sig:
        buf[0x08:0x08+len(SIG)] = SIG
    buf[HDR:HDR+len(payload)] = payload
    s = 0
    for off in range(0, total - 4, 4):
        s = (s + struct.unpack_from(">I", buf, off)[0]) & 0xFFFFFFFF
    struct.pack_into(">I", buf, total - 4, (~s) & 0xFFFFFFFF)
    return bytes(buf)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: draytek_boot_wrap.py <payload@0x80020000> <out.bin>")
    out = build(open(sys.argv[1], "rb").read())
    open(sys.argv[2], "wb").write(out)
    print("wrote %s: 0x%X bytes, word0=0x%08X cksum=0x%08X, payload@0x100 entry=0x%08X"
          % (sys.argv[2], len(out), struct.unpack(">I", out[:4])[0],
             struct.unpack(">I", out[-4:])[0], ENTRY))
