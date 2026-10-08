# Vigor2860-owrt
# DrayTek Vigor 2860 — OpenWrt tree files

The OpenWrt-side of the Vigor 2860 port (the U-Boot board patch lives in
`../uboot/`). These files + edits add two build targets:

- the **`draytek_vigor2860`** device (DTS, NAND layout, image recipe), and
- a **combined factory image** (`...-squashfs-factory.bin`) that the stock
  DrayTek bootloader (DrayBoot) can flash over TFTP — it bundles U-Boot +
  kernel + rootfs and self-installs to NAND on first boot.

> **Status:** OpenWrt boots from NAND, persists (UBI overlay), USB works.
> **Ethernet is working on 2 ports (WAN and LAN 1) — the remaining 5 LAN ports are behind an external
> **QCA8337** switch that isn't driven yet (no `qca8k`, no DTS node)
> **DSL** not working

Compiled image: openwrt-lantiq-xrx200-draytek_vigor2860-squashfs-factory.bin
- Hold reset while powering the router to start TFTP load
- Connect ethernet cable to LAN 1 (other work for TFTP but won't work for Openwrt)
- on host: tftp 192.168.1.1; binary; put openwrt-lantiq-xrx200-draytek_vigor2860-squashfs-factory.bin

To revert to stock - download the official DrayTek firmware

## Prerequisites

An OpenWrt tree that still ships `package/boot/uboot-lantiq/` (board patches
`0100`–`0116` present) — the `uboot-lantiq` package was removed from mainline,
so this needs an older release or a tree where it's been re-added:

```sh
ls package/boot/uboot-lantiq/patches/0116-*.patch   # must exist
```

Built/tested against OpenWrt **24.10-SNAPSHOT r29278** (kernel 6.6.157).

## What's here

```
files/
  vr9_draytek_vigor2860.dts   drop-in DTS (NAND partitions, soft ECC, ttyLTQ0)
  draytek_boot_wrap.py        wraps U-Boot+kernel+rootfs into a DrayBoot image
  vigor2860-u-boot.bin        prebuilt U-Boot the image recipe embeds (see note)
snippets/
  vr9.mk.device               the Device/draytek_vigor2860 block to paste
  uboot-lantiq.Makefile       the two uboot-lantiq Makefile edits to paste
  02_network.edits            
```

## Install

### 1. U-Boot board patch (from ../uboot/)

```sh
cp ../uboot/0117-add-board-DrayTek-Vigor-2860.patch \
   package/boot/uboot-lantiq/patches/
```

### 2. uboot-lantiq Makefile edits

`package/boot/uboot-lantiq/Makefile` — apply the two edits in
`snippets/uboot-lantiq.Makefile`:
- add the `U-Boot/vigor2860_ram` build stanza
- append `vigor2860_ram` to `UBOOT_TARGETS`

(These live in the package Makefile, so they're not captured by the quilt
patch and must be done by hand.)

### 3. Drop-in files

```sh
cp files/vr9_draytek_vigor2860.dts \
   target/linux/lantiq/files/arch/mips/boot/dts/lantiq/
cp files/draytek_boot_wrap.py        scripts/
chmod +x scripts/draytek_boot_wrap.py
cp files/vigor2860-u-boot.bin        target/linux/lantiq/image/
```

### 4. Image recipe

`target/linux/lantiq/image/vr9.mk` — paste the `Build/draytek-combined`
definition and the `Device/draytek_vigor2860` block from
`snippets/vr9.mk.device` (replace the existing `draytek_vigor2860` stub if one
is present).

### 5. Config

```sh
make menuconfig
#  - Target System  : Lantiq
#  - Subtarget      : XRX200
#  - Target Profile : DrayTek Vigor 2860   (or enable the device)
#  - Target Images  : enable  [*] squashfs   <-- REQUIRED, else no ubi/factory image
```

Or on the command line:

```sh
echo 'CONFIG_TARGET_lantiq_xrx200_DEVICE_draytek_vigor2860=y' >> .config
echo 'CONFIG_TARGET_ROOTFS_SQUASHFS=y' >> .config
make defconfig
```

## The prebuilt `vigor2860-u-boot.bin`

The image recipe reads this prebuilt U-Boot and embeds it in the combined
image (this avoids wiring a cross-package build dependency for now). It must be
regenerated whenever the U-Boot `0117` patch changes:

```sh
make package/boot/uboot-lantiq/{clean,compile} V=s
cp $(find build_dir -path '*vigor2860_ram*' -name u-boot.bin | head -1) \
   target/linux/lantiq/image/vigor2860-u-boot.bin
```

Keep the committed `.bin` in sync with the `0117` patch, or the flashed U-Boot
won't match the source.

## Build

```sh
make target/linux/install V=s          # or a full `make`
```

Outputs under `bin/targets/lantiq/xrx200/`:
- `...-draytek_vigor2860-squashfs-factory.bin`   — **first install** (via DrayBoot TFTP)
- `...-draytek_vigor2860-squashfs-sysupgrade.bin` — **later updates** (via `sysupgrade`)
- `...-draytek_vigor2860-initramfs-kernel.bin`    — UART bring-up / `loady`

## Flash (first install)

TFTP the **factory** image to DrayBoot (filename must **not** end in `0`):

```
- connect UART (3.3 V), console = 115200
- power on with the RESET button held
- laptop -> 192.168.1.10
- tftp 192.168.1.1 ; binary ; put <factory>.bin
```

DrayBoot writes it to NAND (primary 0x1380000 + backup 0x3380000). First boot:
U-Boot shrinks DrayBoot's slot to U-Boot-only, reads the kernel from NAND, and
boots OpenWrt; UBI attaches and the overlay is created. Keep the backup slot
intact so a failure drops to DrayBoot recovery rather than bricking.

Console: **`ttyLTQ1`** in DrayBoot/U-Boot, **`ttyLTQ0`** in Linux.

## NAND layout

```
0x0000000  drayboot-vendor  0x1380000  (DrayTek, read-only)
0x1380000  u-boot           0x0100000  (DrayBoot slot, read-only)
0x1480000  kernel           0x0400000  (uImage lzma)
0x1880000  ubi              0x1B00000  (squashfs rootfs + rootfs_data overlay)
```

These must match in three places: this layout, the DTS `partition@…` nodes,
and U-Boot's `bootcmd`.

## Ethernet

**2 of 7 ports working** via the VR9 internal GPHYs:

- `lan1` — PHY at MDIO 0x1c, GSWIP port 2
- `wan`  — PHY at MDIO 0x1e, GSWIP port 4

Key facts (for anyone debugging this):
- The internal GPHYs are at MDIO **0x1c / 0x1e** (from the DrayOS boot log),
  NOT 0x11/0x13 — those addresses respond with garbage because they're the
  undriven QCA8337.
- They must sit on GSWIP ports **2 and 4**: the xrx200 gswip driver only
  advertises `phy-mode = "internal"` on ports 2/3/4/6 (see
  `gswip_xrx200_phylink_get_caps`), so ports 0/1 fail validation with -EINVAL.
- **DSL is disabled** in `02_network` for this board (ethernet WAN). Without
  that, `lantiq_setup_dsl_helper` forces `wan=dsl0/pppoe` and overrides the
  ethernet config.

### TODO
- **5 LAN jacks behind a QCA8337-AL3C switch** — not driven yet. Needs
  `kmod-qca8k`, a cascaded DSA node in the DTS (VR9 RGMII trunk →
  qca8k), and the separate WAN path. No existing lantiq board cascades qca8k.
- **MAC address is random each boot** — no NVMEM source wired. The base MAC
  (00:1D:AA:5C:48:A0) lives in the DrayBoot SPI-NOR bdinfo @ 0x3FFF8; reading
  it from the drayboot-vendor partition is a future improvement.


## License

Derived from OpenWrt / `uboot-lantiq` (GPL-2.0+); GPL-2.0+ accordingly.
