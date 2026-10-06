# Loader (secondary bootloader) for the image

This is the actual machine code that runs on the router. Written in MIPS assembly because at this point there's no C runtime, no OS, no stack — just bare metal.

It does five things in sequence:

1. Copy itself to the top of RAM (0x87EE0000)
The kernel is around 18MB and gets copied to 0x80002000. That range overlaps with where the stub is sitting (0x80020000). If we didn't move out of the way first, the kernel copy would overwrite the stub's own code mid-execution and crash. So the very first thing it does is clone itself somewhere safe, then jump into that copy.

2. Copy the kernel from the TFTP buffer to 0x80002000
DrayBoot loaded the entire TFTP file into RAM at 0x80800000 and left it there. The stub reaches into that buffer (at offset 0x8100, past the DrayBoot header) and copies the 18MB kernel binary down to where the kernel expects to be.

3. Copy the DTB to __appended_dtb
The DTB is the hardware description file — it tells the kernel what's on the board (RAM size, serial port, ethernet, USB, PCIe). The kernel looks for it at a fixed symbol address (0x811770A0). The stub copies it there from the TFTP buffer, right after the kernel binary.

4. Flush the CPU caches
The kernel data was written through the data cache (write-back on the 34Kc). The instruction cache doesn't know about those writes. If we jumped to the kernel now, the CPU might fetch stale instructions from before. The SYNCI loop forces both caches into sync over the entire kernel range.

5. Jump to the kernel entry point
Clears the argument registers and jumps to 0x807D5960. From here the kernel takes over completely.


# The linker script (stub.ld)

It tells the linker three things:

1. Where in memory the code lives

. = 0x80020000;

This tells the linker "assume this code will run at address 0x80020000". That's the address DrayBoot copies the payload to and executes. Without this, the linker defaults to address 0, so every li $8, some_label would compute the wrong address and the relocation jump would go to the wrong place.

2. How to arrange the sections
It puts .text (code), .rodata (constants), and .data (variables) in order. For our stub there's only .text, but the linker needs to be told explicitly.

3. What to throw away
The /DISCARD/ block drops MIPS-specific metadata sections (.reginfo, .pdr, etc.) and debug info that the toolchain adds automatically. Without discarding them, objcopy -O binary would include them in stub.bin and bloat it.

The ASSERT at the end is a sanity check — if the stub ever grows past 0x7FFC bytes, the linker errors out instead of silently producing a binary that DrayBoot would reject.
