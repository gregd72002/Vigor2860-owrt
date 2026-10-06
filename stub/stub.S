/*
 * stub.S -- Vigor 2860 DrayBoot second-stage loader (parametrised)
 *
 * Variable constants use sentinel values (0xDEADxxxx).
 * pack_loader.py reads the real values from vmlinux-initramfs.elf
 * and patches them into stub.bin before assembling the TFTP image.
 * Rebuild stub.bin only if the stub logic itself changes.
 */

/* --- sentinels (patched by pack_loader.py) --- */
#define KERN_LOAD    0x80002000   /* fixed by MIPS ABI, never changes          */
#define KERN_ENTRY   0xDEAD0001   /* patched: ELF entry point                  */
#define KERN_SRC_W   0xDEAD0002   /* patched: KERN_FILESZ / 4                  */
#define DTB_SRC      0xDEAD0003   /* patched: TFTP_BASE + 0x8100 + KERN_FILESZ */
#define DTB_DST      0xDEAD0004   /* patched: __appended_dtb address           */
#define DTB_SIZE_W   0xDEAD0005   /* patched: DTB file size / 4                */
#define SYNCI_END    0xDEAD0006   /* patched: DTB_DST + DTB_SIZE               */

/* --- fixed constants --- */
#define KERN_SRC     0x80808100   /* TFTP_BASE(0x80800000) + DrayBoot hdr(0x8100) */
#define SELF_SRC     0x80020000   /* where DrayBoot executes us                */
#define SELF_W       0x00002000   /* 0x8000 bytes / 4                          */
#define RELOC_BASE   0x87EE0000   /* high RAM, safe from kernel copy           */
#define RELOC_STK    0x87EF0000

.section .text
.global _start
.set noreorder
.set noat

_start:
    /* disable interrupts */
    mfc0    $8, $12
    ori     $8, $8, 0x1
    xori    $8, $8, 0x1
    mtc0    $8, $12
    ehb

    li      $29, (SELF_SRC - 16)

    /* Phase 1: relocate stub to high RAM */
    li      $8,  RELOC_BASE
    li      $9,  SELF_SRC
    li      $10, SELF_W
.Lcopy_self:
    lw      $11, 0($9)
    addiu   $9,  $9,  4
    sw      $11, 0($8)
    addiu   $10, $10, -1
    bnez    $10, .Lcopy_self
     addiu  $8,  $8,  4

    li      $29, RELOC_STK

    /* jump to relocated copy of .Lmain */
    la      $8, .Lmain
    li      $9, SELF_SRC
    subu    $8, $8, $9
    li      $9, RELOC_BASE
    addu    $8, $8, $9
    jr      $8
     nop

.Lmain:
    /* Phase 2: copy kernel from TFTP buffer to load address */
    li      $8,  KERN_LOAD
    li      $9,  KERN_SRC
    li      $10, KERN_SRC_W        /* sentinel: patched to KERN_FILESZ/4 */
.Lcopy_kern:
    lw      $11, 0($9)
    addiu   $9,  $9,  4
    sw      $11, 0($8)
    addiu   $10, $10, -1
    bnez    $10, .Lcopy_kern
     addiu  $8,  $8,  4

    /* Phase 3: copy DTB to __appended_dtb */
    li      $8,  DTB_DST           /* sentinel: patched */
    li      $9,  DTB_SRC           /* sentinel: patched */
    li      $10, DTB_SIZE_W        /* sentinel: patched */
.Lcopy_dtb:
    lw      $11, 0($9)
    addiu   $9,  $9,  4
    sw      $11, 0($8)
    addiu   $10, $10, -1
    bnez    $10, .Lcopy_dtb
     addiu  $8,  $8,  4

    /* Phase 4: SYNCI loop */
    rdhwr   $25, $1
    bnez    $25, .Ldo_synci
     nop
    li      $25, 32
.Ldo_synci:
    li      $8,  KERN_LOAD
    li      $9,  SYNCI_END         /* sentinel: patched */
.Lsynci_loop:
    synci   0($8)
    addu    $8,  $8,  $25
    sltu    $11, $8,  $9
    bnez    $11, .Lsynci_loop
     nop
    sync
    ehb

    /* Phase 5: jump to kernel */
    move    $4,  $0
    move    $5,  $0
    move    $6,  $0
    move    $7,  $0
    li      $8,  KERN_ENTRY        /* sentinel: patched */
    jr      $8
     nop
