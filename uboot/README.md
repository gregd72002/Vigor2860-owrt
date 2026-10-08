# DrayTek Vigor 2860 — U-Boot (Lantiq VR9 / xRX200)

A board port adding **DrayTek Vigor 2860** support to OpenWrt's `uboot-lantiq`
package. The resulting U-Boot is a **RAM variant chainloaded by the stock
DrayTek bootloader (DrayBoot)** — DrayBoot stays in place on SPI-NOR and loads
this U-Boot from NAND, so the device is never bricked and the vendor recovery
path is preserved.

Considering Ethernet is not fully working, the only way to uplaod a kernel is through UART.

v2860-draytek-uboot.bin should be fully complete and ready to TFTP into the router.
It will overwrite NAND content (DrayOS). 
This is reversable - TFTP original Vigor 2860 firmware from Draytek support website.
 

## Status

| Component | State |
|-----------|-------|
| Boot + persistence (flashed to NAND, chainloaded by DrayBoot) | ✅ works |
| Serial console (`ttyLTQ1`, 115200) | ✅ works |
| NAND (Toshiba TC58NVG0S3ETA00, 128 MiB) | ✅ detected / read / write |
| Ethernet — link + RX (internal GPHYs) | ✅ works |
| Ethernet — CPU-side TX | ❌ **TODO** (link up, RX ok, CPU TX silent) |

Ethernet TX is the one open item: the switch forwards inbound frames (activity
LEDs blink), but the CPU/GMAC egress path isn't initialised, so `tftpboot`
doesn't work yet. The CPU-port / GMAC-TX init that DrayBoot performs still needs
to be replicated (or left to OpenWrt's GSWIP driver once Linux boots). The four
external-switch jacks are intentionally **not** configured here — that belongs
in the OpenWrt DTS, which has the real GSWIP/switch drivers.

## Board facts

- SoC: Lantiq **VRX268 v1.2** (VR9 / xRX200), 600 MHz
- RAM: 128 MiB (inited by DrayBoot — U-Boot runs with `SKIP_LOWLEVEL_INIT`)
- Bootloader on SPI-NOR (DrayBoot); NAND holds config + firmware + data
- Cloned from the ZyXEL **P-2812HNU-Fx** board (closest VR9 + NAND reference)
- `CONFIG_SYS_TEXT_BASE = 0xA0020000` — the uncached KSEG1 alias of DrayBoot's
  CodeStart (`0x80020000`); DrayBoot copies the payload there and jumps
- GPHY firmware: **`phy11g_a2x`** (the v1.4+ stepping; the stock p2812hnufx
  config loads `a1x`, which does not link on this chip)
- Base MAC (from DrayBoot SPI-NOR bdinfo @ `0x3FFF8`): `00:1D:AA:5C:48:A0`

## Built against

- **U-Boot:** `2013.10-openwrt4` (the version `uboot-lantiq` pulls in)
- **OpenWrt:** `v24.10.8-44-g58584c6f28/58584c6f2829a7e5d77376ab68aae3dcc4a392d8`

  Find and record yours so this is reproducible:
  ```sh
  git -C /path/to/openwrt describe --tags --always
  grep -E 'VERSION_(NUMBER|CODE)' /path/to/openwrt/include/version.mk
  ```

> **Important compatibility note.** `uboot-lantiq` (with U-Boot 2013.10 and the
> `01xx` board patches) was **removed from mainline OpenWrt** years ago. This
> port only applies to a tree that still ships `package/boot/uboot-lantiq/`
> (board patches `0100`–`0116` present). That means an older OpenWrt release, or
> a tree where the package has been re-added. Confirm before starting:
> ```sh
> ls package/boot/uboot-lantiq/patches/0116-*.patch
> ```

## Repository contents

```
0117-add-board-DrayTek-Vigor-2860.patch   # the board port (quilt patch for U-Boot)
README.md                                 # this file
```

The `0117` patch adds, inside the U-Boot source tree:
`board/draytek/vigor2860/` (Makefile, config.mk, ddr_settings.h, vigor2860.c),
`include/configs/vigor2860.h`, and the `vigor2860_ram` row in `boards.cfg`.

## Applying

### 1. Drop in the patch

```sh
cp 0117-add-board-DrayTek-Vigor-2860.patch \
   package/boot/uboot-lantiq/patches/
```

It must sort **after** `0116` so it applies last in the series. The
`boards.cfg` row is part of this patch — **do not** edit `boards.cfg` by hand.

### 2. Edit `package/boot/uboot-lantiq/Makefile`

These two edits live in the OpenWrt package Makefile, *not* in the U-Boot
source, so they are **not** captured by the patch and must be done manually.

Add the build stanza (next to the `U-Boot/p2812hnufx_ram` one):

```make
define U-Boot/vigor2860_ram
  NAME:=DrayTek Vigor 2860 (RAM)
  BUILD_SUBTARGET:=xrx200
  DDR_SETTINGS:=board/draytek/vigor2860/ddr_settings.h
endef
```

Append `vigor2860_ram` to the `UBOOT_TARGETS:=` list:

```make
UBOOT_TARGETS:= \
	... \
	p2812hnufx_ram p2812hnufx_nandspl \
	vigor2860_ram \
	...
```

`BUILD_DEVICES` is intentionally omitted — it ties the build to an image target
that doesn't exist yet. Without it the U-Boot builds standalone.

### 3. Verify it reconstitutes from a clean unpack

```sh
make package/boot/uboot-lantiq/{clean,prepare} V=s
# no .rej / FAILED in the output, and:
find build_dir -path '*u-boot-2013.10/board/draytek/vigor2860'
grep -n vigor2860 build_dir/*/u-boot-*/u-boot-2013.10/boards.cfg
grep -n 0xA0020000 build_dir/*/u-boot-*/u-boot-2013.10/include/configs/vigor2860.h
```

All three should report the board. If you see a `.rej`, the fragile hunk is the
second `boards.cfg` edit (0116 then 0117 touch the same file) — regenerate it
against your tree's `boards.cfg`.

## Building

Fast iteration — build U-Boot directly in the extracted tree (no packaging):

```sh
cd build_dir/target-*/u-boot-*/u-boot-2013.10/
export CROSS_COMPILE=$(ls -d /path/to/openwrt/staging_dir/toolchain-mips_24kc_musl*/bin)/mips-openwrt-linux-musl-
make vigor2860_ram_config
make u-boot.bin        # -> ./u-boot.bin
```

Or via the package (output under `bin/targets/lantiq/xrx200/`):

```sh
make package/boot/uboot-lantiq/compile V=s
```

## Flashing / deploying

The raw `u-boot.bin` must be wrapped in DrayBoot's firmware container before
DrayBoot will accept it: a 0x100-byte header (`word0` = total length), the
payload padded to `0x80000`, and a trailing one's-complement checksum. Wrap it,
then TFTP the `.bin` to DrayBoot's upgrade prompt — it writes the primary
(`0x1380000`) and backup (`0x3380000`) firmware slots and boots the new image.


Once wrapped (out.bin):

- rename out.bin to v2860_uboot.bin (it needs .bin extension and the filename cannot have '0' at the end as it triggers different processing path)
- connect UART cable (3.3v)
- start router with RESET button pressed
- set you laptop address to 192.168.1.10
- from laptop: tftp 192.168.1.1; binary; put out.bin
- done


## License

The board files are derived from `uboot-lantiq` (GPL-2.0+); this port is
GPL-2.0+ accordingly.
