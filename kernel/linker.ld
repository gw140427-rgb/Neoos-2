ENTRY(_start)
SECTIONS {
    . = 0x40000000;
    .text.boot : { *(.text.boot) }
    .text : { *(.text) }
    .rodata : { *(.rodata) }
    .data : { *(.data) }
    .bss : { *(.bss) }
    . = . + 0x8000;
    _stack_top = .;
}
