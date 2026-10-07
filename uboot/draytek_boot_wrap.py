#!/usr/bin/env python3
# Build a DrayBoot-acceptable image for the Vigor 2860.
#
# Two modes:
#
#   uboot-only  (dev / RAM chainload, or a plain U-Boot flash image)
#     --uboot u-boot.bin --out v2860_uboot.bin
#       0x000  word0 (BE) = total length
#       0x008  "rDkmfaaryTedecz" signature (TFTP FW_MODE_BIN detection)
#       0x100  U-Boot payload (linked/entered at 0x80020000, <= 0x80000)
#       end-4  ~(sum of preceding BE words)
#
#   combined    (one-shot factory installer: U-Boot + kernel + rootfs)
#     --uboot u-boot.bin --kernel uImage --rootfs root.ubi --out v2860_factory.bin
#
# -------------------------------------------------------------------------
# How the combined image works with DrayBoot and the self-converting U-Boot
# -------------------------------------------------------------------------
# DrayBoot's TFTP flash-upgrade writes word0 bytes verbatim to the primary
# slot at NAND 0x1380000 (and mirrors to the backup slot 0x3380000), after
# checking word0 == file size and verifying the one's-complement checksum.
# On boot it re-reads word0 bytes, re-verifies that checksum, copies a FIXED
# 0x80000 from image+0x100 to CodeStart 0x80020000, and jumps.
#
# Because the slot is written verbatim, blob offset == NAND offset - 0x1380000.
# We lay the pieces out so each lands on its final NAND block boundary:
#
#   blob 0x000000  header (word0 + signature)          NAND 0x1380000
#   blob 0x000100  U-Boot, padded to 0x80000           NAND 0x1380100
#   blob 0x080100  (pad) <- shrunk checksum lands here  NAND 0x1400100
#   blob 0x100000  kernel uImage, padded to KPART       NAND 0x1480000
#   blob 0x100000+KPART  rootfs (ubi)                   NAND 0x1480000+KPART
#   end-4          full-image ~sum checksum
#
# First boot: DrayBoot checksums the WHOLE blob (passes, nothing changed yet)
# and enters U-Boot. board_late_init() rewrites word0 -> 0x80104 and the
# checksum at blob 0x80100 so DrayBoot thereafter checksums U-Boot ONLY. The
# kernel and rootfs are then outside DrayBoot's view and freely writable by
# OpenWrt (overlay, sysupgrade). The pad word at blob 0x80100 is what the hook
# overwrites, so nothing real is clobbered.
#
# NOTE the two offsets below MUST match include/configs/vigor2860.h:
#   UBOOT_LEN == 0x80104, CHECKSUM_OFFSET == 0x80100, KERNEL @ NAND 0x1480000.
# And the kernel/rootfs NAND offsets printed at the end MUST match the OpenWrt
# fixed-partitions DTS.
from __future__ import annotations   # allow 'bytes | None' hints on Python < 3.10
import sys, struct, argparse

SIG          = b"rDkmfaaryTedecz"
HDR          = 0x100
COPY         = 0x80000        # fixed bytes DrayBoot copies+executes from image+0x100
ENTRY        = 0x80020000
SLOT_BASE    = 0x1380000      # NAND offset DrayBoot writes the blob to (primary)
UBOOT_REGION = 0x100000       # header+uboot+pad; kernel starts at end of this (NAND 0x1480000)
DEFAULT_KPART= 0x400000       # kernel partition size (rootfs starts after it)
CAP          = 0x2000000      # 32 MiB slot cap enforced by DrayBoot

# Post-conversion values produced by board_late_init() - kept here only to
# assert the layout stays consistent with the hook.
POST_UBOOT_LEN   = HDR + COPY + 4   # 0x80104
POST_CKSUM_OFF   = HDR + COPY       # 0x80100  (must fall inside the uboot region pad)
assert POST_CKSUM_OFF < UBOOT_REGION, "shrunk checksum would land outside the U-Boot region"
assert HDR + COPY <= UBOOT_REGION,    "U-Boot region too small for header+payload"


def _finalize(buf: bytearray) -> bytes:
    """Set word0 = total length and the trailing one's-complement checksum."""
    if len(buf) % 4:
        buf += b"\x00" * (4 - len(buf) % 4)
    buf += b"\x00\x00\x00\x00"              # checksum slot
    total = len(buf)
    if total > CAP:
        raise SystemExit("image 0x%X > 0x%X (32 MiB slot cap)" % (total, CAP))
    struct.pack_into(">I", buf, 0, total)
    s = 0
    for off in range(0, total - 4, 4):
        s = (s + struct.unpack_from(">I", buf, off)[0]) & 0xFFFFFFFF
    struct.pack_into(">I", buf, total - 4, (~s) & 0xFFFFFFFF)
    return bytes(buf)


def build_uboot(uboot: bytes, add_sig=True) -> bytes:
    if len(uboot) > COPY:
        raise SystemExit("U-Boot 0x%X > 0x%X (512 KiB fixed copy)" % (len(uboot), COPY))
    buf = bytearray(HDR + ((len(uboot) + 3) & ~3))
    if add_sig:
        buf[0x08:0x08 + len(SIG)] = SIG
    buf[HDR:HDR + len(uboot)] = uboot
    return _finalize(buf)


def build_combined(uboot: bytes, kernel: bytes, rootfs: bytes | None,
                   kpart=DEFAULT_KPART, add_sig=True):
    if len(uboot) > COPY:
        raise SystemExit("U-Boot 0x%X > 0x%X (512 KiB fixed copy)" % (len(uboot), COPY))
    if len(kernel) > kpart:
        raise SystemExit("kernel 0x%X > kernel partition 0x%X "
                         "(raise --kernel-part-size and the DTS to match)"
                         % (len(kernel), kpart))
    if rootfs is None:
        sys.stderr.write("WARNING: no --rootfs given; a non-initramfs kernel will "
                         "have no root filesystem to mount.\n")

    # U-Boot region: header + payload, zero-padded to UBOOT_REGION so the
    # kernel starts exactly at NAND 0x1480000.
    buf = bytearray(UBOOT_REGION)
    if add_sig:
        buf[0x08:0x08 + len(SIG)] = SIG
    buf[HDR:HDR + len(uboot)] = uboot

    # Kernel region: padded to kpart so rootfs starts on its block boundary.
    buf += kernel + b"\x00" * (kpart - len(kernel))

    rootfs_blob = UBOOT_REGION + kpart      # == NAND rootfs off - SLOT_BASE
    if rootfs:
        buf += rootfs

    img = _finalize(buf)
    return img, UBOOT_REGION, rootfs_blob


def _report(path, img, kernel_blob=None, rootfs_blob=None, have_rootfs=False):
    word0 = struct.unpack(">I", img[:4])[0]
    cksum = struct.unpack(">I", img[-4:])[0]
    print("wrote %s" % path)
    print("  total 0x%06X  word0 0x%08X  cksum 0x%08X  (cap headroom 0x%X)"
          % (len(img), word0, cksum, CAP - len(img)))
    print("  NAND map (blob written verbatim from 0x%06X):" % SLOT_BASE)
    print("    0x%07X  u-boot   (entry 0x%08X)" % (SLOT_BASE + HDR, ENTRY))
    if kernel_blob is not None:
        print("    0x%07X  kernel   <- DTS 'kernel' partition start" % (SLOT_BASE + kernel_blob))
    if rootfs_blob is not None:
        tag = "" if have_rootfs else "  (empty - no rootfs supplied)"
        print("    0x%07X  ubi/root <- DTS 'ubi' partition start%s" % (SLOT_BASE + rootfs_blob, tag))
    print("  after first-boot conversion by board_late_init():")
    print("    word0 -> 0x%08X   shrunk cksum word @ NAND 0x%07X"
          % (POST_UBOOT_LEN, SLOT_BASE + POST_CKSUM_OFF))


def main():
    ap = argparse.ArgumentParser(description="DrayBoot image wrapper for the Vigor 2860")
    ap.add_argument("--uboot", required=True, help="u-boot.bin (linked @ 0x80020000, <= 512 KiB)")
    ap.add_argument("--kernel", help="kernel uImage; switches to combined-installer mode")
    ap.add_argument("--rootfs", help="rootfs image (ubi) appended after the kernel partition")
    ap.add_argument("--out", required=True, help="output .bin")
    ap.add_argument("--kernel-part-size", type=lambda x: int(x, 0), default=DEFAULT_KPART,
                    help="kernel partition size (default 0x400000; keep DTS in sync)")
    ap.add_argument("--no-sig", action="store_true", help="omit the FW_MODE_BIN signature")
    a = ap.parse_args()

    uboot = open(a.uboot, "rb").read()
    add_sig = not a.no_sig

    if a.kernel:
        kernel = open(a.kernel, "rb").read()
        rootfs = open(a.rootfs, "rb").read() if a.rootfs else None
        img, kblob, rblob = build_combined(uboot, kernel, rootfs,
                                           kpart=a.kernel_part_size, add_sig=add_sig)
        open(a.out, "wb").write(img)
        _report(a.out, img, kblob, rblob, have_rootfs=rootfs is not None)
    else:
        if a.rootfs:
            raise SystemExit("--rootfs requires --kernel")
        img = build_uboot(uboot, add_sig=add_sig)
        open(a.out, "wb").write(img)
        _report(a.out, img)


if __name__ == "__main__":
    main()
