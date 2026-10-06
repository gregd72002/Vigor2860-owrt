# Makefile -- Vigor 2860 second-stage loader stub
#
# Uses the toolchain built by OpenWrt (no extra installs needed).
# Run from inside the Docker container at /work/loader/

OWRT     := /work
TC       := $(OWRT)/staging_dir/toolchain-mips_24kc_gcc-13.3.0_musl/bin
CROSS    := $(TC)/mips-openwrt-linux-musl-

AS       := $(CROSS)gcc
LD       := $(CROSS)ld
OBJCOPY  := $(CROSS)objcopy
OBJDUMP  := $(CROSS)objdump
NM       := $(CROSS)nm
SIZE     := $(CROSS)size

ASFLAGS  := -x assembler-with-cpp -march=mips32r2 -mabi=32 -EB -nostdlib -nostartfiles -c

.PHONY: all clean disasm check_dtb_sym

all: stub.bin

stub.o: stub.S
	$(AS) $(ASFLAGS) -o $@ $<

stub.elf: stub.o stub.ld
	$(LD) -T stub.ld -o $@ $<
	$(SIZE) $@

stub.bin: stub.elf
	$(OBJCOPY) -O binary $< $@
	@echo "Stub size: $$(wc -c < $@) bytes (max 32764 / 0x7FFC)"
	@if [ "$$(wc -c < $@)" -gt 32764 ]; then echo "ERROR: stub too large"; exit 1; fi

# Show disassembly (useful for verifying relocation logic)
disasm: stub.elf
	$(OBJDUMP) -d $<

# Check where the kernel expects its appended DTB.
# Should print a line containing __appended_dtb.
# If the address matches 0x812b722c (BSS end) -- stub is correct as-is.
# If it matches 0x811770a0 (file data end) -- remove the BSS-zero phase
# from stub.S and change DTB_DST to 0x811770A0.
check_dtb_sym:
	$(NM) $(OWRT)/build_dir/target-mips_24kc_musl/linux-lantiq_xrx200/vmlinux-initramfs.elf \
	    | grep -E '__appended_dtb|^[0-9a-f]+ . _end$$|__bss_stop' \
	    | sort

clean:
	rm -f stub.o stub.elf stub.bin
