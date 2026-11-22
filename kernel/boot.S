// NeoOS entry stub: normalize whatever state the firmware/loader handed
// over before relying on memory. The first instructions perform NO data
// loads (the old code started with a literal-pool load of the stack
// address, which faults when the handoff state is not the expected one);
// every address below is built from immediates or PC-relative arithmetic.
//
// Why: EDK2 hands off at EL2 when the machine exposes EL2 (QEMU virt
// with virtualization=on, and Vectras's ARM64 VM). The old stub assumed
// an EL1, MMU-off handoff (true for QEMU -kernel and for EDK2 at EL1),
// so on an EL2 handoff the kernel died with a synchronous exception on
// its very first instruction. This stub now handles the handoff level
// deliberately:
//   EL2 -> grant EL1 timer access, then drop to EL1 (HCR/SPSR/ELR+eret)
//   EL3 -> same idea via SCR/SPSR/ELR (defensive; EDK2 does not use it)
//   EL1 -> straight through
// At EL1 the MMU and caches are forced off in SCTLR_EL1 (physical
// identity addressing, exactly like a QEMU -kernel handoff), the vector
// table is installed immediately, and only then is the stack set up.
.section .text.boot
.global _start
_start:
    msr daifset, #0xf           // mask IRQ/FIQ/SError/debug right away

    mrs x0, CurrentEL
    lsr x0, x0, #2
    and x0, x0, #3              // x0 = current EL (1..3)
    cmp x0, #3
    b.eq .Lfrom_el3
    cmp x0, #2
    b.eq .Lfrom_el2
    b .Lel1_entry               // already at EL1

.Lfrom_el3:
    mov x0, #0x401              // SCR_EL3: NS + RW (EL1 is AArch64)
    msr scr_el3, x0
    mov x0, #0x3c5              // SPSR_EL3: EL1h, all interrupts masked
    msr spsr_el3, x0
    adr x0, .Lel1_entry
    msr elr_el3, x0
    eret

.Lfrom_el2:
    // Do not depend on firmware having granted EL1 access to the
    // physical timer/counter, and give the virtual counter no offset.
    mrs x0, cnthctl_el2
    orr x0, x0, #0x3            // EL1PCTEN | EL1PCEN
    msr cnthctl_el2, x0
    msr cntvoff_el2, xzr
    mov x0, #(1 << 31)          // HCR_EL2.RW: EL1 executes AArch64
    msr hcr_el2, x0
    mov x0, #0x3c5              // SPSR_EL2: EL1h, all interrupts masked
    msr spsr_el2, x0
    adr x0, .Lel1_entry
    msr elr_el2, x0
    eret

.Lel1_entry:
    // Force the EL1 MMU and caches off: a loader may leave its page
    // tables active (EDK2 does); never trust them.
    mrs x0, sctlr_el1
    bic x0, x0, #1              // M:  MMU off
    bic x0, x0, #(1 << 2)       // C:  data cache off
    bic x0, x0, #(1 << 12)      // I:  instruction cache off
    msr sctlr_el1, x0
    tlbi vmalle1
    dsb sy
    isb

    // Install our exception vectors now (kernel_main installs the same
    // table again later; doing it here closes the window where a fault
    // would vector into stale firmware vectors and look like a hang).
    adrp x0, vectors
    add x0, x0, :lo12:vectors
    msr vbar_el1, x0

    // Stack pointer via PC-relative arithmetic (no literal-pool load).
    adrp x0, _stack_top
    add x0, x0, :lo12:_stack_top
    mov sp, x0
    bl kernel_main
hang:
    wfe
    b hang
