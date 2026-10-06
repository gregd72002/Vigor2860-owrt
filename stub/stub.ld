OUTPUT_ARCH(mips)
ENTRY(_start)

SECTIONS
{
    . = 0x80020000;

    .text : {
        *(.text)
        *(.text.*)
    }

    .rodata : {
        *(.rodata)
        *(.rodata.*)
    }

    .data : {
        *(.data)
        *(.data.*)
    }

    /DISCARD/ : {
        *(.reginfo)
        *(.MIPS.options)
        *(.pdr)
        *(.note*)
        *(.comment*)
        *(.gnu*)
    }

    . = ASSERT(. <= 0x80027FFC, "ERROR: stub exceeds DrayBoot payload limit");
}
