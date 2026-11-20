// NeoOS kernel - milestone 3: draw on a real screen (QEMU ramfb framebuffer)
// plus the milestone 2 serial echo. QEMU virt: UART 0x09000000, fw_cfg 0x09020000.
volatile unsigned int *const UART0 = (unsigned int *)0x09000000;

/* ---------- serial (UART) ---------- */
static void uart_putc(char c) { UART0[0] = (unsigned int)c; }
static void uart_puts(const char *s) {
    while (*s) uart_putc(*s++);
}
static char uart_getc(void) {
    while (UART0[6] & 0x10) { /* RXFE: wait for input */ }
    return (char)(UART0[0] & 0xFF);
}
static void uart_putnum(unsigned long v) {
    char buf[24];
    int i = 0;
    if (v == 0) { uart_putc('0'); return; }
    while (v) { buf[i++] = (char)('0' + (v % 10)); v /= 10; }
    while (i) uart_putc(buf[--i]);
}
static void uart_puthex(unsigned long v) {
    const char *h = "0123456789abcdef";
    uart_puts("0x");
    for (int i = 60; i >= 0; i -= 4) uart_putc(h[(v >> i) & 0xF]);
}

/* ---------- milestone 4: GIC + generic timer interrupts ---------- */
static volatile unsigned int *const GICD = (volatile unsigned int *)0x08000000;
static volatile unsigned int *const GICC = (volatile unsigned int *)0x08010000;
static volatile unsigned char *const GICD_PRIO = (volatile unsigned char *)0x08000400;
#define INTID_TIMER 30

static unsigned long ticks = 0;
static unsigned long cntfrq = 0;

static inline unsigned long read_cntfrq(void) {
    unsigned long v; __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(v)); return v;
}
static inline void write_cntp_tval(unsigned long v) {
    __asm__ volatile("msr cntp_tval_el0, %0" :: "r"(v));
}
static inline void write_cntp_ctl(unsigned long v) {
    __asm__ volatile("msr cntp_ctl_el0, %0" :: "r"(v));
}

static void irq_init(void) {
    extern char vectors[];
    __asm__ volatile("msr vbar_el1, %0" :: "r"(vectors));
    GICD[0] = 1;                          // distributor on
    GICD_PRIO[INTID_TIMER] = 0x00;        // highest priority
    GICD[0x100 / 4] |= (1u << INTID_TIMER); // enable INTID 30
    GICC[0] = 1;                          // CPU interface on
    GICC[1] = 0xFF;                       // priority mask: allow all
    cntfrq = read_cntfrq();
    write_cntp_tval(cntfrq);              // first tick in 1 second
    write_cntp_ctl(1);                    // timer on, IRQ unmasked
    __asm__ volatile("msr daifclr, #2");  // unmask IRQ at the CPU
}

/* ---------- milestone 6: preemptive multitasking (2 tasks, switch on tick) ---------- */
struct task {
    unsigned long saved_sp;
};
static struct task tasks[2];
static int current_task = 0;
static int sched_ready = 0;
static unsigned char task_b_stack[16384] __attribute__((aligned(16)));

static void task_b(void) {
    unsigned long n = 0;
    while (1) {
        n++;
        uart_puts("B: ");
        uart_putnum(n);
        uart_putc('\n');
        for (volatile unsigned long i = 0; i < 20000000UL; i++) {
        }
    }
}

static void sched_init(void) {
    unsigned long top = (unsigned long)task_b_stack + sizeof(task_b_stack);
    unsigned long *frame = (unsigned long *)(top - 272);
    for (int i = 0; i < 34; i++) frame[i] = 0;
    frame[248 / 8] = (unsigned long)task_b; // ELR: start at task_b
    frame[256 / 8] = 0x5;                   // SPSR: EL1h, exceptions unmasked
    tasks[1].saved_sp = (unsigned long)frame;
    sched_ready = 1;
    uart_puts("sched on\n");
}

unsigned long irq_dispatch(unsigned long sp) {
    unsigned int iar = GICC[3];           // IAR (0x0C)
    unsigned int id = iar & 0x3FF;
    if (id == INTID_TIMER) {
        ticks++;
        uart_puts("tick ");
        uart_putnum(ticks);
        uart_putc('\n');
        write_cntp_tval(cntfrq);          // rearm for the next second
        GICC[4] = iar;                    // EOIR (0x10)
        if (sched_ready) {
            tasks[current_task].saved_sp = sp;
            current_task = (current_task + 1) % 2;
            return tasks[current_task].saved_sp;
        }
        return sp;
    }
    GICC[4] = iar;                        // EOIR (0x10)
    return sp;
}

void sync_exception_report(void) {
    unsigned long esr, elr;
    __asm__ volatile("mrs %0, esr_el1" : "=r"(esr));
    __asm__ volatile("mrs %0, elr_el1" : "=r"(elr));
    uart_puts("\nSYNC EXCEPTION esr=");
    uart_puthex(esr);
    uart_puts(" elr=");
    uart_puthex(elr);
    uart_putc('\n');
}

/* ---------- fw_cfg (find and write the ramfb config) ---------- */
static volatile unsigned char *const FW_DATA = (volatile unsigned char *)0x09020000;
static volatile unsigned short *const FW_SEL = (volatile unsigned short *)0x09020008;

static unsigned short bswap16(unsigned short v) { return (unsigned short)((v >> 8) | (v << 8)); }
static void fw_select(unsigned short sel) { *FW_SEL = bswap16(sel); }
static unsigned char fw_read8(void) { return *FW_DATA; }
static unsigned int fw_read32be(void) {
    unsigned int v = 0;
    for (int i = 0; i < 4; i++) v = (v << 8) | fw_read8();
    return v;
}
static unsigned short fw_read16be(void) {
    return (unsigned short)((fw_read8() << 8) | fw_read8());
}
static int name_eq(const char *a, const char *b) {
    while (*a && *b && *a == *b) { a++; b++; }
    return *a == *b;
}

// Returns the fw_cfg selector of the named file, or -1.
static int fw_find_file(const char *want) {
    fw_select(0x0019); // FW_CFG_FILE_DIR
    unsigned int count = fw_read32be();
    for (unsigned int i = 0; i < count; i++) {
        unsigned int size = fw_read32be(); (void)size;
        unsigned short sel = fw_read16be();
        fw_read16be(); // reserved
        char name[56];
        for (int j = 0; j < 56; j++) name[j] = (char)fw_read8();
        name[55] = 0;
        if (name_eq(name, want)) return (int)sel;
    }
    return -1;
}

/* ---------- framebuffer ---------- */
#define FB_W 1024
#define FB_H 768
static unsigned int fb[FB_W * FB_H];

/* fw_cfg DMA write: modern QEMU ignores data-port writes, so the ramfb
   config must go through the DMA interface at fw_cfg base + 0x10. */
static unsigned int bswap32(unsigned int v) {
    return ((v & 0xFF) << 24) | ((v & 0xFF00) << 8) | ((v >> 8) & 0xFF00) | ((v >> 24) & 0xFF);
}
static unsigned long long bswap64(unsigned long long v) {
    return ((unsigned long long)bswap32((unsigned int)v) << 32) | bswap32((unsigned int)(v >> 32));
}
struct fw_dma {
    unsigned int control;       // big-endian on the wire
    unsigned int length;        // big-endian
    unsigned long long address; // big-endian
};
static volatile struct fw_dma dma __attribute__((aligned(16)));
static volatile unsigned long long *const FW_DMA = (volatile unsigned long long *)0x09020010;

static void fw_dma_write(int sel, const void *buf, unsigned int len) {
    dma.control = bswap32(((unsigned int)sel << 16) | (1u << 3) | (1u << 4)); // SELECT | WRITE
    dma.length = bswap32(len);
    dma.address = bswap64((unsigned long long)(unsigned long)buf);
    __asm__ volatile("dmb sy" ::: "memory");
    *FW_DMA = bswap64((unsigned long long)(unsigned long)&dma);
    while (bswap32(dma.control) != 0) {
    }
}

static void screen_init(void) {
    int sel = fw_find_file("etc/ramfb");
    if (sel < 0) {
        uart_puts("ramfb not found\n");
        return;
    }
    // Build the config: every field big-endian on the wire (write MSB first).
    unsigned long long addr = (unsigned long long)(unsigned long)fb;
    static unsigned char cfg[28];
    for (int i = 0; i < 8; i++) cfg[i] = (unsigned char)(addr >> (56 - 8 * i));
    unsigned int fields[5] = {0x34325258 /* XR24 = XRGB8888 */, 0, FB_W, FB_H, FB_W * 4};
    for (int f = 0; f < 5; f++)
        for (int i = 0; i < 4; i++)
            cfg[8 + f * 4 + i] = (unsigned char)(fields[f] >> (24 - 8 * i));
    fw_dma_write(sel, cfg, 28);
    uart_puts("screen on\n");
}

static void draw_pixel(int x, int y, unsigned int color) {
    if (x >= 0 && x < FB_W && y >= 0 && y < FB_H) fb[y * FB_W + x] = color;
}
static void fill_rect(int x, int y, int w, int h, unsigned int color) {
    for (int j = y; j < y + h; j++)
        for (int i = x; i < x + w; i++) draw_pixel(i, j, color);
}

/* Tiny 5x7 font: only the letters needed for "NeoOS" */
static const unsigned char glyph_N[7] = {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11};
static const unsigned char glyph_e[7] = {0x00, 0x00, 0x0E, 0x11, 0x1F, 0x10, 0x0E};
static const unsigned char glyph_o[7] = {0x00, 0x00, 0x0E, 0x11, 0x11, 0x11, 0x0E};
static const unsigned char glyph_S[7] = {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E};

static void draw_letter(const unsigned char g[7], int x, int y, int scale, unsigned int color) {
    for (int row = 0; row < 7; row++)
        for (int col = 0; col < 5; col++)
            if (g[row] & (0x10 >> col))
                fill_rect(x + col * scale, y + row * scale, scale, scale, color);
}

static void draw_scene(void) {
    fill_rect(0, 0, FB_W, FB_H, 0x00101828);          // dark blue background
    fill_rect(312, 284, 400, 200, 0x00203040);        // panel
    int x = 352, y = 356, s = 10;
    draw_letter(glyph_N, x, y, s, 0x00FFFFFF); x += 60;
    draw_letter(glyph_e, x, y, s, 0x00FFFFFF); x += 60;
    draw_letter(glyph_o, x, y, s, 0x00FFFFFF); x += 60;
    draw_letter(glyph_o, x, y, s, 0x00FFFFFF); x += 60;
    draw_letter(glyph_S, x, y, s, 0x00FFFFFF);
}

/* ---------- milestone 5: physical page allocator (4KB pages, bitmap) ---------- */
extern char _kernel_end[];
#define PAGE_SIZE 4096UL
#define MEM_END 0x48000000UL /* QEMU virt default 128MB RAM end */
static unsigned char page_bitmap[4096]; /* up to 32768 pages */
static unsigned long mem_base = 0;
static unsigned long mem_pages = 0;
static unsigned long mem_free = 0;

static void mem_init(void) {
    mem_base = ((unsigned long)_kernel_end + PAGE_SIZE - 1) & ~(PAGE_SIZE - 1);
    mem_pages = (MEM_END - mem_base) / PAGE_SIZE;
    mem_free = mem_pages;
    uart_puts("mem: ");
    uart_putnum(mem_pages * PAGE_SIZE / (1024 * 1024));
    uart_puts(" MB managed, ");
    uart_putnum(mem_free);
    uart_puts(" pages free\n");
}

static void *page_alloc(void) {
    for (unsigned long i = 0; i < mem_pages; i++) {
        if (!(page_bitmap[i / 8] & (1u << (i % 8)))) {
            page_bitmap[i / 8] |= (unsigned char)(1u << (i % 8));
            mem_free--;
            unsigned long addr = mem_base + i * PAGE_SIZE;
            unsigned long *p = (unsigned long *)addr;
            for (unsigned long j = 0; j < PAGE_SIZE / 8; j++) p[j] = 0;
            return (void *)addr;
        }
    }
    return 0;
}

static void page_free(void *ptr) {
    unsigned long i = ((unsigned long)ptr - mem_base) / PAGE_SIZE;
    if (page_bitmap[i / 8] & (1u << (i % 8))) {
        page_bitmap[i / 8] &= (unsigned char)~(1u << (i % 8));
        mem_free++;
    }
}

static void mem_selftest(void) {
    void *a = page_alloc();
    void *b = page_alloc();
    void *c = page_alloc();
    uart_puts("alloc a=");
    uart_puthex((unsigned long)a);
    uart_puts(" b=");
    uart_puthex((unsigned long)b);
    uart_puts(" c=");
    uart_puthex((unsigned long)c);
    uart_putc('\n');
    unsigned int *w = (unsigned int *)a;
    w[0] = 0xDEADBEEF;
    w[1023] = 0x12345678;
    page_free(b);
    void *d = page_alloc();
    uart_puts("freed b, realloc d=");
    uart_puthex((unsigned long)d);
    uart_puts(d == b ? " (reused)\n" : " (NOT reused)\n");
    if (w[0] == 0xDEADBEEF && w[1023] == 0x12345678)
        uart_puts("mem test ok\n");
    else
        uart_puts("mem test FAIL\n");
    page_free(a);
    page_free(c);
    page_free(d);
}

/* ---------- main ---------- */
void kernel_main(void) {
    uart_puts("NeoOS kernel: boot ok\n");
    irq_init();
    uart_puts("timer on\n");
    mem_init();
    mem_selftest();
    sched_init();
    screen_init();
    draw_scene();
    uart_puts("Type something and press Enter.\n");
    uart_puts("neo> ");
    while (1) {
        char c = uart_getc();
        if (c == '\r') c = '\n';
        uart_putc(c);
        if (c == '\n') uart_puts("neo> ");
    }
}
