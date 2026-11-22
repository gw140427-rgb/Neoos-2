// NeoOS kernel - milestone 8: GUI (window manager + system apps) on top of
// milestones 1-7 (boot, serial shell, ramfb, timer IRQ, page allocator,
// preemptive multitasking, RAM filesystem). QEMU virt platform.
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

static int fb_ready = 0;
static void disp_flush(void); /* defined in the virtio-gpu section below */
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
    fb_ready = 1;
    uart_puts("screen on\n");
}

static void draw_pixel(int x, int y, unsigned int color) {
    if (x >= 0 && x < FB_W && y >= 0 && y < FB_H) fb[y * FB_W + x] = color;
}
static void fill_rect(int x, int y, int w, int h, unsigned int color) {
    int x0 = x < 0 ? 0 : x, y0 = y < 0 ? 0 : y;
    int x1 = x + w > FB_W ? FB_W : x + w, y1 = y + h > FB_H ? FB_H : y + h;
    for (int j = y0; j < y1; j++) {
        unsigned int *row = &fb[j * FB_W];
        for (int i = x0; i < x1; i++) row[i] = color;
    }
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
    disp_flush();
}

/* ---------- milestone 8: full 8x8 font + text drawing ----------
   Glyphs: public-domain IBM VGA 8x8 font (font8x8_basic, chars 32..126).
   One byte per row, bit j (1<<j) is the pixel at column j. */
static const unsigned char font8x8[95][8] = {
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0x18, 0x3C, 0x3C, 0x18, 0x18, 0x00, 0x18, 0x00},
    {0x36, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0x36, 0x36, 0x7F, 0x36, 0x7F, 0x36, 0x36, 0x00},
    {0x0C, 0x3E, 0x03, 0x1E, 0x30, 0x1F, 0x0C, 0x00},
    {0x00, 0x63, 0x33, 0x18, 0x0C, 0x66, 0x63, 0x00},
    {0x1C, 0x36, 0x1C, 0x6E, 0x3B, 0x33, 0x6E, 0x00},
    {0x06, 0x06, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0x18, 0x0C, 0x06, 0x06, 0x06, 0x0C, 0x18, 0x00},
    {0x06, 0x0C, 0x18, 0x18, 0x18, 0x0C, 0x06, 0x00},
    {0x00, 0x66, 0x3C, 0xFF, 0x3C, 0x66, 0x00, 0x00},
    {0x00, 0x0C, 0x0C, 0x3F, 0x0C, 0x0C, 0x00, 0x00},
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C, 0x06},
    {0x00, 0x00, 0x00, 0x3F, 0x00, 0x00, 0x00, 0x00},
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C, 0x00},
    {0x60, 0x30, 0x18, 0x0C, 0x06, 0x03, 0x01, 0x00},
    {0x3E, 0x63, 0x73, 0x7B, 0x6F, 0x67, 0x3E, 0x00},
    {0x0C, 0x0E, 0x0C, 0x0C, 0x0C, 0x0C, 0x3F, 0x00},
    {0x1E, 0x33, 0x30, 0x1C, 0x06, 0x33, 0x3F, 0x00},
    {0x1E, 0x33, 0x30, 0x1C, 0x30, 0x33, 0x1E, 0x00},
    {0x38, 0x3C, 0x36, 0x33, 0x7F, 0x30, 0x78, 0x00},
    {0x3F, 0x03, 0x1F, 0x30, 0x30, 0x33, 0x1E, 0x00},
    {0x1C, 0x06, 0x03, 0x1F, 0x33, 0x33, 0x1E, 0x00},
    {0x3F, 0x33, 0x30, 0x18, 0x0C, 0x0C, 0x0C, 0x00},
    {0x1E, 0x33, 0x33, 0x1E, 0x33, 0x33, 0x1E, 0x00},
    {0x1E, 0x33, 0x33, 0x3E, 0x30, 0x18, 0x0E, 0x00},
    {0x00, 0x0C, 0x0C, 0x00, 0x00, 0x0C, 0x0C, 0x00},
    {0x00, 0x0C, 0x0C, 0x00, 0x00, 0x0C, 0x0C, 0x06},
    {0x18, 0x0C, 0x06, 0x03, 0x06, 0x0C, 0x18, 0x00},
    {0x00, 0x00, 0x3F, 0x00, 0x00, 0x3F, 0x00, 0x00},
    {0x06, 0x0C, 0x18, 0x30, 0x18, 0x0C, 0x06, 0x00},
    {0x1E, 0x33, 0x30, 0x18, 0x0C, 0x00, 0x0C, 0x00},
    {0x3E, 0x63, 0x7B, 0x7B, 0x7B, 0x03, 0x1E, 0x00},
    {0x0C, 0x1E, 0x33, 0x33, 0x3F, 0x33, 0x33, 0x00},
    {0x3F, 0x66, 0x66, 0x3E, 0x66, 0x66, 0x3F, 0x00},
    {0x3C, 0x66, 0x03, 0x03, 0x03, 0x66, 0x3C, 0x00},
    {0x1F, 0x36, 0x66, 0x66, 0x66, 0x36, 0x1F, 0x00},
    {0x7F, 0x46, 0x16, 0x1E, 0x16, 0x46, 0x7F, 0x00},
    {0x7F, 0x46, 0x16, 0x1E, 0x16, 0x06, 0x0F, 0x00},
    {0x3C, 0x66, 0x03, 0x03, 0x73, 0x66, 0x7C, 0x00},
    {0x33, 0x33, 0x33, 0x3F, 0x33, 0x33, 0x33, 0x00},
    {0x1E, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x1E, 0x00},
    {0x78, 0x30, 0x30, 0x30, 0x33, 0x33, 0x1E, 0x00},
    {0x67, 0x66, 0x36, 0x1E, 0x36, 0x66, 0x67, 0x00},
    {0x0F, 0x06, 0x06, 0x06, 0x46, 0x66, 0x7F, 0x00},
    {0x63, 0x77, 0x7F, 0x7F, 0x6B, 0x63, 0x63, 0x00},
    {0x63, 0x67, 0x6F, 0x7B, 0x73, 0x63, 0x63, 0x00},
    {0x1C, 0x36, 0x63, 0x63, 0x63, 0x36, 0x1C, 0x00},
    {0x3F, 0x66, 0x66, 0x3E, 0x06, 0x06, 0x0F, 0x00},
    {0x1E, 0x33, 0x33, 0x33, 0x3B, 0x1E, 0x38, 0x00},
    {0x3F, 0x66, 0x66, 0x3E, 0x36, 0x66, 0x67, 0x00},
    {0x1E, 0x33, 0x07, 0x0E, 0x38, 0x33, 0x1E, 0x00},
    {0x3F, 0x2D, 0x0C, 0x0C, 0x0C, 0x0C, 0x1E, 0x00},
    {0x33, 0x33, 0x33, 0x33, 0x33, 0x33, 0x3F, 0x00},
    {0x33, 0x33, 0x33, 0x33, 0x33, 0x1E, 0x0C, 0x00},
    {0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00},
    {0x63, 0x63, 0x36, 0x1C, 0x1C, 0x36, 0x63, 0x00},
    {0x33, 0x33, 0x33, 0x1E, 0x0C, 0x0C, 0x1E, 0x00},
    {0x7F, 0x63, 0x31, 0x18, 0x4C, 0x66, 0x7F, 0x00},
    {0x1E, 0x06, 0x06, 0x06, 0x06, 0x06, 0x1E, 0x00},
    {0x03, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x40, 0x00},
    {0x1E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x1E, 0x00},
    {0x08, 0x1C, 0x36, 0x63, 0x00, 0x00, 0x00, 0x00},
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF},
    {0x0C, 0x0C, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00},
    {0x00, 0x00, 0x1E, 0x30, 0x3E, 0x33, 0x6E, 0x00},
    {0x07, 0x06, 0x06, 0x3E, 0x66, 0x66, 0x3B, 0x00},
    {0x00, 0x00, 0x1E, 0x33, 0x03, 0x33, 0x1E, 0x00},
    {0x38, 0x30, 0x30, 0x3E, 0x33, 0x33, 0x6E, 0x00},
    {0x00, 0x00, 0x1E, 0x33, 0x3F, 0x03, 0x1E, 0x00},
    {0x1C, 0x36, 0x06, 0x0F, 0x06, 0x06, 0x0F, 0x00},
    {0x00, 0x00, 0x6E, 0x33, 0x33, 0x3E, 0x30, 0x1F},
    {0x07, 0x06, 0x36, 0x6E, 0x66, 0x66, 0x67, 0x00},
    {0x0C, 0x00, 0x0E, 0x0C, 0x0C, 0x0C, 0x1E, 0x00},
    {0x30, 0x00, 0x30, 0x30, 0x30, 0x33, 0x33, 0x1E},
    {0x07, 0x06, 0x66, 0x36, 0x1E, 0x36, 0x67, 0x00},
    {0x0E, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x1E, 0x00},
    {0x00, 0x00, 0x33, 0x7F, 0x7F, 0x6B, 0x63, 0x00},
    {0x00, 0x00, 0x1F, 0x33, 0x33, 0x33, 0x33, 0x00},
    {0x00, 0x00, 0x1E, 0x33, 0x33, 0x33, 0x1E, 0x00},
    {0x00, 0x00, 0x3B, 0x66, 0x66, 0x3E, 0x06, 0x0F},
    {0x00, 0x00, 0x6E, 0x33, 0x33, 0x3E, 0x30, 0x78},
    {0x00, 0x00, 0x3B, 0x6E, 0x66, 0x06, 0x0F, 0x00},
    {0x00, 0x00, 0x3E, 0x03, 0x1E, 0x30, 0x1F, 0x00},
    {0x08, 0x0C, 0x3E, 0x0C, 0x0C, 0x2C, 0x18, 0x00},
    {0x00, 0x00, 0x33, 0x33, 0x33, 0x33, 0x6E, 0x00},
    {0x00, 0x00, 0x33, 0x33, 0x33, 0x1E, 0x0C, 0x00},
    {0x00, 0x00, 0x63, 0x6B, 0x7F, 0x7F, 0x36, 0x00},
    {0x00, 0x00, 0x63, 0x36, 0x1C, 0x36, 0x63, 0x00},
    {0x00, 0x00, 0x33, 0x33, 0x33, 0x3E, 0x30, 0x1F},
    {0x00, 0x00, 0x3F, 0x19, 0x0C, 0x26, 0x3F, 0x00},
    {0x38, 0x0C, 0x0C, 0x07, 0x0C, 0x0C, 0x38, 0x00},
    {0x18, 0x18, 0x18, 0x00, 0x18, 0x18, 0x18, 0x00},
    {0x07, 0x0C, 0x0C, 0x38, 0x0C, 0x0C, 0x07, 0x00},
    {0x6E, 0x3B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
};

static void draw_char(int x, int y, char c, int scale, unsigned int color) {
    unsigned char uc = (unsigned char)c;
    if (uc < 32 || uc > 126) uc = '?';
    const unsigned char *g = font8x8[uc - 32];
    for (int row = 0; row < 8; row++)
        for (int col = 0; col < 8; col++)
            if (g[row] & (1u << col))
                fill_rect(x + col * scale, y + row * scale, scale, scale, color);
}
static void draw_text(int x, int y, const char *s, int scale, unsigned int color) {
    while (*s) { draw_char(x, y, *s++, scale, color); x += 8 * scale; }
}
static int text_w(const char *s, int scale) {
    int n = 0;
    while (s[n]) n++;
    return n * 8 * scale;
}
static char *u2s(unsigned long v, char *buf) {
    char tmp[24];
    int i = 0, j = 0;
    if (v == 0) tmp[i++] = '0';
    while (v) { tmp[i++] = (char)('0' + (v % 10)); v /= 10; }
    while (i) buf[j++] = tmp[--i];
    buf[j] = 0;
    return buf;
}
static void clock_str(unsigned long t, char *buf) { /* uptime as HH:MM:SS */
    unsigned long h = (t / 3600) % 100, m = (t / 60) % 60, s = t % 60;
    buf[0] = (char)('0' + h / 10); buf[1] = (char)('0' + h % 10); buf[2] = ':';
    buf[3] = (char)('0' + m / 10); buf[4] = (char)('0' + m % 10); buf[5] = ':';
    buf[6] = (char)('0' + s / 10); buf[7] = (char)('0' + s % 10); buf[8] = 0;
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

/* Shell output sink: 0 = UART (serial shell), 1 = GUI terminal window.
   term_* are defined in the milestone 8 section below. */
static int out_to_term = 0;
static void term_putc(char c);
static void term_clear(void);
static void sh_putc(char c) { if (out_to_term) term_putc(c); else uart_putc(c); }
static void sh_puts(const char *s) { while (*s) sh_putc(*s++); }
static void sh_putnum(unsigned long v) {
    char buf[24];
    int i = 0;
    if (v == 0) { sh_putc('0'); return; }
    while (v) { buf[i++] = (char)('0' + (v % 10)); v /= 10; }
    while (i) sh_putc(buf[--i]);
}

/* ---------- milestone 7: RAM filesystem + shell ---------- */
static int streq(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

#define FS_MAX_FILES 16
#define FS_MAX_PAGES 16
#define FS_NAME_MAX 28
struct fs_file {
    int used;
    char name[FS_NAME_MAX];
    unsigned long size;
    void *pages[FS_MAX_PAGES];
};
static struct fs_file fs_files[FS_MAX_FILES];

static int fs_find(const char *name) {
    for (int i = 0; i < FS_MAX_FILES; i++)
        if (fs_files[i].used && streq(fs_files[i].name, name)) return i;
    return -1;
}
static int fs_create(const char *name) {
    int idx = fs_find(name);
    if (idx >= 0) { /* truncate existing */
        for (int p = 0; p < FS_MAX_PAGES; p++)
            if (fs_files[idx].pages[p]) { page_free(fs_files[idx].pages[p]); fs_files[idx].pages[p] = 0; }
        fs_files[idx].size = 0;
        return idx;
    }
    for (int i = 0; i < FS_MAX_FILES; i++) {
        if (!fs_files[i].used) {
            fs_files[i].used = 1;
            for (int j = 0; j < FS_NAME_MAX - 1 && name[j]; j++) fs_files[i].name[j] = name[j];
            fs_files[i].name[FS_NAME_MAX - 1] = 0;
            fs_files[i].size = 0;
            for (int p = 0; p < FS_MAX_PAGES; p++) fs_files[i].pages[p] = 0;
            return i;
        }
    }
    return -1;
}
static int fs_append_byte(int idx, char ch) {
    struct fs_file *f = &fs_files[idx];
    unsigned long pi = f->size / PAGE_SIZE;
    if (pi >= FS_MAX_PAGES) return -1;
    if (!f->pages[pi]) {
        f->pages[pi] = page_alloc();
        if (!f->pages[pi]) return -1;
    }
    ((char *)f->pages[pi])[f->size % PAGE_SIZE] = ch;
    f->size++;
    return 0;
}
static void fs_delete(int idx) {
    for (int p = 0; p < FS_MAX_PAGES; p++)
        if (fs_files[idx].pages[p]) { page_free(fs_files[idx].pages[p]); fs_files[idx].pages[p] = 0; }
    fs_files[idx].used = 0;
    fs_files[idx].size = 0;
}

/* copy the next space-separated token from *cursor into buf; advance cursor */
static void next_token(const char **cursor, char *buf, int bufsz) {
    const char *s = *cursor;
    while (*s == ' ') s++;
    int i = 0;
    while (*s && *s != ' ' && i < bufsz - 1) buf[i++] = *s++;
    buf[i] = 0;
    while (*s == ' ') s++;
    *cursor = s;
}

static void shell_exec(char *line) {
    const char *cur = line;
    char cmd[32];
    next_token(&cur, cmd, sizeof(cmd));
    if (streq(cmd, "help")) {
        sh_puts("commands: help ls write cat rm mem clear\n");
    } else if (streq(cmd, "ls")) {
        int any = 0;
        for (int i = 0; i < FS_MAX_FILES; i++) {
            if (fs_files[i].used) {
                sh_puts(fs_files[i].name);
                sh_puts("  ");
                sh_putnum(fs_files[i].size);
                sh_puts(" bytes\n");
                any = 1;
            }
        }
        if (!any) sh_puts("(no files)\n");
    } else if (streq(cmd, "write")) {
        char name[FS_NAME_MAX];
        next_token(&cur, name, sizeof(name));
        if (!name[0]) { sh_puts("usage: write <name> <text>\n"); return; }
        int idx = fs_create(name);
        if (idx < 0) { sh_puts("fs full\n"); return; }
        while (*cur) fs_append_byte(idx, *cur++);
        sh_puts("ok\n");
    } else if (streq(cmd, "cat")) {
        char name[FS_NAME_MAX];
        next_token(&cur, name, sizeof(name));
        int idx = fs_find(name);
        if (idx < 0) { sh_puts("no such file\n"); return; }
        struct fs_file *f = &fs_files[idx];
        for (unsigned long i = 0; i < f->size; i++)
            sh_putc(((char *)f->pages[i / PAGE_SIZE])[i % PAGE_SIZE]);
        sh_putc('\n');
    } else if (streq(cmd, "rm")) {
        char name[FS_NAME_MAX];
        next_token(&cur, name, sizeof(name));
        int idx = fs_find(name);
        if (idx < 0) { sh_puts("no such file\n"); return; }
        fs_delete(idx);
        sh_puts("removed\n");
    } else if (streq(cmd, "mem")) {
        sh_putnum(mem_free);
        sh_puts(" pages free\n");
    } else if (streq(cmd, "clear")) {
        if (out_to_term) term_clear(); else draw_scene();
        sh_puts("screen redrawn\n");
    } else {
        sh_puts("unknown command: ");
        sh_puts(cmd);
        sh_putc('\n');
    }
}

static void shell(void) {
    char line[128];
    uart_puts("NeoOS shell. Type 'help'.\n");
    while (1) {
        uart_puts("neo> ");
        int n = 0;
        while (1) {
            char c = uart_getc();
            if (c == '\r') c = '\n';
            uart_putc(c);
            if (c == '\n') break;
            if (n < 127) line[n++] = c;
        }
        line[n] = 0;
        if (n == 0) continue;
        shell_exec(line);
    }
}

/* ---------- milestone 8: virtio-input, window manager, GUI apps ---------- */
static int gui_dirty = 1;
static int mouse_x = 512, mouse_y = 384, mouse_btn = 0;

/* --- input queue (virtio keyboard + UART both feed this) --- */
static char inq[128];
static int inq_head = 0, inq_tail = 0;
static void inq_push(char c) {
    int n = (inq_tail + 1) % 128;
    if (n != inq_head) { inq[inq_tail] = c; inq_tail = n; }
}
static int inq_pop(void) {
    if (inq_head == inq_tail) return -1;
    char c = inq[inq_head];
    inq_head = (inq_head + 1) % 128;
    return (int)(unsigned char)c;
}

/* --- keyboard translation (Linux keycodes -> ASCII) --- */
static int kb_shift = 0;
static const char kb_map[58] = {
    0, 27, '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=', 8, 9,
    'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']', '\n', 0,
    'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', '\'', '`', 0, '\\',
    'z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/', 0, '*', 0, ' '
};
static char kb_shifted(char c) {
    if (c >= 'a' && c <= 'z') return (char)(c - 32);
    switch (c) {
        case '1': return '!'; case '2': return '@'; case '3': return '#';
        case '4': return '$'; case '5': return '%'; case '6': return '^';
        case '7': return '&'; case '8': return '*'; case '9': return '(';
        case '0': return ')'; case '-': return '_'; case '=': return '+';
        case '[': return '{'; case ']': return '}'; case ';': return ':';
        case '\'': return '"'; case '`': return '~'; case '\\': return '|';
        case ',': return '<'; case '.': return '>'; case '/': return '?';
    }
    return c;
}
static void kb_event(unsigned int code, int value) {
    if (code == 42 || code == 54) { kb_shift = (value != 0); return; }
    if (value == 0 || code >= 58) return; /* key up / out of map */
    char c = kb_map[code];
    if (kb_shift) c = kb_shifted(c);
    if (c) inq_push(c);
}

/* --- terminal window text grid --- */
#define TERM_COLS 37
#define TERM_ROWS 18
static char tgrid[TERM_ROWS][TERM_COLS];
static int tcur_x = 0, tcur_y = 0;

static void term_clear(void) {
    for (int y = 0; y < TERM_ROWS; y++)
        for (int x = 0; x < TERM_COLS; x++) tgrid[y][x] = ' ';
    tcur_x = 0;
    tcur_y = 0;
}
static void term_scroll(void) {
    for (int y = 0; y < TERM_ROWS - 1; y++)
        for (int x = 0; x < TERM_COLS; x++) tgrid[y][x] = tgrid[y + 1][x];
    for (int x = 0; x < TERM_COLS; x++) tgrid[TERM_ROWS - 1][x] = ' ';
}
static void term_putc(char c) {
    if (c == '\n') { tcur_x = 0; tcur_y++; }
    else if (c == '\r') { tcur_x = 0; }
    else if (c >= 32 && c < 127) {
        tgrid[tcur_y][tcur_x] = c;
        if (++tcur_x >= TERM_COLS) { tcur_x = 0; tcur_y++; }
    }
    if (tcur_y >= TERM_ROWS) { term_scroll(); tcur_y = TERM_ROWS - 1; }
    gui_dirty = 1;
}
static void term_puts(const char *s) { while (*s) term_putc(*s++); }

static char term_line[128];
static int term_line_len = 0;
static void term_erase(void) {
    if (tcur_x > 0) tcur_x--;
    else if (tcur_y > 0) { tcur_y--; tcur_x = TERM_COLS - 1; }
    tgrid[tcur_y][tcur_x] = ' ';
    gui_dirty = 1;
}
static void term_key(char c) {
    if (c == '\n') {
        term_putc('\n');
        term_line[term_line_len] = 0;
        if (term_line_len > 0) {
            out_to_term = 1;
            shell_exec(term_line);
            out_to_term = 0;
        }
        term_line_len = 0;
        term_puts("neo> ");
    } else if (c == 8 || c == 127) {
        if (term_line_len > 0) { term_line_len--; term_erase(); }
    } else if (c >= 32 && c < 127) {
        if (term_line_len < 127) { term_line[term_line_len++] = c; term_putc(c); }
    }
    gui_dirty = 1;
}

/* --- window manager --- */
enum { W_TERM, W_INFO, W_FILES, W_SETTINGS };
struct window { int x, y, w, h, kind; const char *title; };
static struct window wins[4];
static int zord[4]; /* draw order: zord[3] is topmost (focused) */
static int drag_win = -1, drag_dx = 0, drag_dy = 0;
static unsigned int desktop_color = 0x00101828;
static const unsigned int swatches[4] = {0x00101828, 0x00142A18, 0x002A1830, 0x00332A18};
static const char *swatch_names[4] = {"Navy", "Forest", "Plum", "Bronze"};
static int swatch_sel = 0;

static void wm_init(void) {
    wins[W_TERM] = (struct window){24, 48, 624, 330, W_TERM, "Terminal"};
    wins[W_INFO] = (struct window){664, 48, 336, 176, W_INFO, "System Info"};
    wins[W_FILES] = (struct window){664, 248, 336, 200, W_FILES, "Files"};
    wins[W_SETTINGS] = (struct window){300, 428, 340, 180, W_SETTINGS, "Settings"};
    zord[0] = W_INFO; zord[1] = W_FILES; zord[2] = W_SETTINGS; zord[3] = W_TERM;
}
static void wm_raise(int wi) {
    int pos = 0;
    for (int i = 0; i < 4; i++) if (zord[i] == wi) pos = i;
    for (int i = pos; i < 3; i++) zord[i] = zord[i + 1];
    zord[3] = wi;
}
static void settings_click(struct window *w, int x, int y) {
    for (int i = 0; i < 4; i++) {
        int sx = w->x + 16 + i * 56, sy = w->y + 62;
        if (x >= sx && x < sx + 44 && y >= sy && y < sy + 44) {
            swatch_sel = i;
            desktop_color = swatches[i];
        }
    }
}
static void wm_press(int x, int y) {
    for (int zi = 3; zi >= 0; zi--) {
        int wi = zord[zi];
        struct window *w = &wins[wi];
        if (x >= w->x && x < w->x + w->w && y >= w->y && y < w->y + w->h) {
            wm_raise(wi);
            if (y < w->y + 22) {
                drag_win = wi;
                drag_dx = x - w->x;
                drag_dy = y - w->y;
            } else if (w->kind == W_SETTINGS) {
                settings_click(w, x, y);
            }
            gui_dirty = 1;
            return;
        }
    }
}
static void wm_release(void) { drag_win = -1; gui_dirty = 1; }
static void wm_drag_update(void) {
    if (drag_win < 0) return;
    struct window *w = &wins[drag_win];
    int nx = mouse_x - drag_dx, ny = mouse_y - drag_dy;
    if (nx < 0) nx = 0;
    if (nx > FB_W - 80) nx = FB_W - 80;
    if (ny < 28) ny = 28;
    if (ny > FB_H - 40) ny = FB_H - 40;
    w->x = nx;
    w->y = ny;
}

static void buf_add(char *b, const char *s) {
    int i = 0;
    while (b[i]) i++;
    while (*s) b[i++] = *s++;
    b[i] = 0;
}
static void buf_addnum(char *b, unsigned long v) {
    char tmp[24];
    u2s(v, tmp);
    buf_add(b, tmp);
}
static void rect_outline(int x, int y, int w, int h, unsigned int color) {
    fill_rect(x, y, w, 2, color);
    fill_rect(x, y + h - 2, w, 2, color);
    fill_rect(x, y, 2, h, color);
    fill_rect(x + w - 2, y, 2, h, color);
}

static void draw_term_content(struct window *w, int focused) {
    for (int r = 0; r < TERM_ROWS; r++)
        for (int c = 0; c < TERM_COLS; c++) {
            char ch = tgrid[r][c];
            if (ch != ' ')
                draw_char(w->x + 8 + c * 16, w->y + 27 + r * 16, ch, 2, 0x00A8E6A0);
        }
    if (focused)
        fill_rect(w->x + 8 + tcur_x * 16, w->y + 27 + tcur_y * 16 + 14, 14, 2, 0x00A8E6A0);
}
static void draw_info_content(struct window *w) {
    char buf[48], clk[12];
    int x = w->x + 12, y = w->y + 30;
    draw_text(x, y, "NeoOS stage 8 GUI", 2, 0x00FFFFFF); y += 20;
    clock_str(ticks, clk);
    buf[0] = 0; buf_add(buf, "Uptime "); buf_add(buf, clk);
    draw_text(x, y, buf, 2, 0x00C0D8E8); y += 20;
    buf[0] = 0; buf_add(buf, "Free pages "); buf_addnum(buf, mem_free);
    draw_text(x, y, buf, 2, 0x00C0D8E8); y += 20;
    buf[0] = 0; buf_add(buf, "Free RAM "); buf_addnum(buf, mem_free / 256); buf_add(buf, " MB");
    draw_text(x, y, buf, 2, 0x00C0D8E8); y += 20;
    draw_text(x, y, "Tasks 2 (preemptive)", 2, 0x00C0D8E8); y += 20;
    buf[0] = 0; buf_add(buf, "Mouse "); buf_addnum(buf, (unsigned long)mouse_x);
    buf_add(buf, ", "); buf_addnum(buf, (unsigned long)mouse_y);
    draw_text(x, y, buf, 2, 0x00C0D8E8);
}
static void draw_files_content(struct window *w) {
    int y = w->y + 30, any = 0;
    for (int i = 0; i < FS_MAX_FILES; i++) {
        if (!fs_files[i].used) continue;
        if (y + 16 > w->y + w->h - 6) break;
        any = 1;
        char buf[48];
        buf[0] = 0;
        buf_add(buf, fs_files[i].name);
        buf_add(buf, "  ");
        buf_addnum(buf, fs_files[i].size);
        buf_add(buf, " B");
        draw_text(w->x + 12, y, buf, 2, 0x00D8E8F0);
        y += 20;
    }
    if (!any) draw_text(w->x + 12, y, "(no files)", 2, 0x00809098);
}
static void draw_settings_content(struct window *w) {
    draw_text(w->x + 16, w->y + 32, "Desktop background", 2, 0x00FFFFFF);
    for (int i = 0; i < 4; i++) {
        int sx = w->x + 16 + i * 56, sy = w->y + 62;
        fill_rect(sx, sy, 44, 44, swatches[i]);
        if (i == swatch_sel) rect_outline(sx - 2, sy - 2, 48, 48, 0x00FFFFFF);
    }
    draw_text(w->x + 16, w->y + 122, swatch_names[swatch_sel], 2, 0x00C0D0D8);
}

static const char *cursor_shape[16] = {
    "X...........", "XX..........", "XXX.........", "XXXX........",
    "XXXXX.......", "XXXXXX......", "XXXXXXX.....", "XXXXXXXX....",
    "XXXXXXXXX...", "XXXXXXXXXX..", "XXXXXX......", "XXX.XXX.....",
    "XX...XXX....", "X.....XXX...", "......XXX...", "......XX...."
};
static void draw_cursor(void) {
    for (int pass = 0; pass < 2; pass++) {
        unsigned int col = pass == 0 ? 0x00000000 : 0x00FFFFFF;
        int o = pass == 0 ? 1 : 0;
        for (int r = 0; r < 16; r++)
            for (int c = 0; c < 12; c++)
                if (cursor_shape[r][c] == 'X')
                    draw_pixel(mouse_x + o + c, mouse_y + o + r, col);
    }
}

static void wm_redraw(void) {
    fill_rect(0, 0, FB_W, FB_H, desktop_color);
    fill_rect(0, 0, FB_W, 26, 0x00202838);
    draw_text(10, 5, "NeoOS", 2, 0x00FFFFFF);
    char clk[12];
    clock_str(ticks, clk);
    draw_text(FB_W - 10 - text_w(clk, 2), 5, clk, 2, 0x00C0D8E8);
    for (int zi = 0; zi < 4; zi++) {
        struct window *w = &wins[zord[zi]];
        int foc = (zi == 3);
        fill_rect(w->x, w->y, w->w, w->h, 0x00607080);
        fill_rect(w->x + 1, w->y + 1, w->w - 2, 21, foc ? 0x002A5A8A : 0x00304050);
        draw_text(w->x + 8, w->y + 4, w->title, 2, 0x00FFFFFF);
        fill_rect(w->x + 1, w->y + 22, w->w - 2, w->h - 23, 0x000E1418);
        switch (w->kind) {
            case W_TERM: draw_term_content(w, foc); break;
            case W_INFO: draw_info_content(w); break;
            case W_FILES: draw_files_content(w); break;
            case W_SETTINGS: draw_settings_content(w); break;
        }
    }
    draw_cursor();
}

/* --- virtio-input driver (virtio-mmio, event queue, polled) --- */
#define VI_QN 32
struct vi_event { unsigned short type, code; unsigned int value; };
struct vring_desc { unsigned long long addr; unsigned int len; unsigned short flags, next; };
struct vring_avail { unsigned short flags, idx, ring[VI_QN], used_event; };
struct vring_used_elem { unsigned int id, len; };
struct vring_used { unsigned short flags, idx; struct vring_used_elem ring[VI_QN]; unsigned short avail_event; };

struct vi_dev {
    volatile unsigned int *r;
    int version, is_tablet, is_keyboard;
    int abs_min_x, abs_max_x, abs_min_y, abs_max_y;
    struct vi_event ev[VI_QN];
    struct vring_desc *desc;
    struct vring_avail *avail;
    struct vring_used *used;
    unsigned short avail_idx, used_idx;
};
static unsigned char vq_mem[2][8192] __attribute__((aligned(4096)));
static struct vi_dev vi_devs[2];
static int vi_count = 0;

static int str_contains(const char *s, const char *sub) {
    for (int i = 0; s[i]; i++) {
        int j = 0;
        while (sub[j] && s[i + j] == sub[j]) j++;
        if (!sub[j]) return 1;
    }
    return 0;
}
static unsigned char vi_cfg_rd8(struct vi_dev *d, unsigned int off) {
    return *(volatile unsigned char *)((unsigned long)d->r + 0x100 + off);
}
static void vi_cfg_wr8(struct vi_dev *d, unsigned int off, unsigned char v) {
    *(volatile unsigned char *)((unsigned long)d->r + 0x100 + off) = v;
}
static unsigned int vi_cfg_rd32(struct vi_dev *d, unsigned int off) {
    return *(volatile unsigned int *)((unsigned long)d->r + 0x100 + off);
}
static void vi_read_name(struct vi_dev *d, char *buf, int bufsz) {
    vi_cfg_wr8(d, 0, 0x01); /* VIRTIO_INPUT_CFG_ID_NAME */
    vi_cfg_wr8(d, 1, 0);
    int sz = vi_cfg_rd8(d, 2);
    if (sz > bufsz - 1) sz = bufsz - 1;
    if (sz < 0) sz = 0;
    for (int i = 0; i < sz; i++) buf[i] = (char)vi_cfg_rd8(d, 8 + i);
    buf[sz] = 0;
}
static void vi_abs_info(struct vi_dev *d, int axis, int *mn, int *mx) {
    vi_cfg_wr8(d, 0, 0x12); /* VIRTIO_INPUT_CFG_ABS_INFO */
    vi_cfg_wr8(d, 1, (unsigned char)axis);
    *mn = (int)vi_cfg_rd32(d, 8);
    *mx = (int)vi_cfg_rd32(d, 12);
}

static int vi_setup_queue(struct vi_dev *d, unsigned char *mem) {
    volatile unsigned int *r = d->r;
    r[0x30 / 4] = 0; /* QueueSel: eventq */
    if (r[0x34 / 4] == 0) return -1; /* QueueNumMax */
    r[0x38 / 4] = VI_QN; /* QueueNum */
    unsigned int align = (d->version == 1) ? r[0x3C / 4] : 4096; /* QueueAlign */
    if (align == 0) align = 4096;
    unsigned int avail_off = VI_QN * 16;
    unsigned int used_off = avail_off + 6 + 2 * VI_QN;
    used_off = (used_off + align - 1) & ~(align - 1);
    d->desc = (struct vring_desc *)mem;
    d->avail = (struct vring_avail *)(mem + avail_off);
    d->used = (struct vring_used *)(mem + used_off);
    for (int i = 0; i < VI_QN; i++) {
        d->desc[i].addr = (unsigned long)&d->ev[i];
        d->desc[i].len = 8;
        d->desc[i].flags = 2; /* VRING_DESC_F_WRITE */
        d->desc[i].next = 0;
        d->avail->ring[i] = (unsigned short)i;
    }
    d->avail->flags = 0;
    d->avail->idx = VI_QN;
    d->used->flags = 0;
    d->used->idx = 0;
    d->avail_idx = VI_QN;
    d->used_idx = 0;
    __asm__ volatile("dmb sy" ::: "memory");
    if (d->version == 1) {
        /* GuestPageSize must be programmed first: QEMU's virtio-mmio
           defaults guest_page_shift to 0 and would otherwise treat the
           PFN itself as the queue address (events then never arrive). */
        r[0x28 / 4] = 4096; /* VIRTIO_MMIO_GUEST_PAGE_SIZE */
        r[0x40 / 4] = (unsigned int)((unsigned long)mem / 4096); /* QueuePFN */
    } else {
        unsigned long m = (unsigned long)mem;
        r[0x80 / 4] = (unsigned int)m;         r[0x84 / 4] = (unsigned int)(m >> 32);
        r[0x90 / 4] = (unsigned int)(unsigned long)d->avail;
        r[0x94 / 4] = (unsigned int)((unsigned long)d->avail >> 32);
        r[0xA0 / 4] = (unsigned int)(unsigned long)d->used;
        r[0xA4 / 4] = (unsigned int)((unsigned long)d->used >> 32);
        r[0x44 / 4] = 1; /* QueueReady */
    }
    return 0;
}

static void vi_handle_event(struct vi_dev *d, struct vi_event *ev) {
    if (d->is_tablet) {
        if (ev->type == 3) { /* EV_ABS */
            if (ev->code == 0) { /* ABS_X */
                long range = (long)d->abs_max_x - d->abs_min_x;
                if (range <= 0) range = 32767;
                long v = (long)(int)ev->value - d->abs_min_x;
                int px = (int)(v * (FB_W - 1) / range);
                mouse_x = px < 0 ? 0 : (px > FB_W - 1 ? FB_W - 1 : px);
                wm_drag_update();
                gui_dirty = 1;
            } else if (ev->code == 1) { /* ABS_Y */
                long range = (long)d->abs_max_y - d->abs_min_y;
                if (range <= 0) range = 32767;
                long v = (long)(int)ev->value - d->abs_min_y;
                int py = (int)(v * (FB_H - 1) / range);
                mouse_y = py < 0 ? 0 : (py > FB_H - 1 ? FB_H - 1 : py);
                wm_drag_update();
                gui_dirty = 1;
            }
        } else if (ev->type == 1 && ev->code == 0x110) { /* BTN_LEFT */
            int v = ev->value ? 1 : 0;
            if (v != mouse_btn) {
                mouse_btn = v;
                if (v) wm_press(mouse_x, mouse_y); else wm_release();
                gui_dirty = 1;
            }
        }
    } else if (d->is_keyboard) {
        if (ev->type == 1) kb_event(ev->code, (int)ev->value); /* EV_KEY */
    }
}

static void vi_poll(struct vi_dev *d) {
    volatile unsigned int *r = d->r;
    unsigned int isr = r[0x60 / 4]; /* InterruptStatus */
    if (isr) r[0x64 / 4] = isr;     /* InterruptACK */
    int kicked = 0;
    __asm__ volatile("dmb sy" ::: "memory");
    while (d->used_idx != d->used->idx) {
        struct vring_used_elem e = d->used->ring[d->used_idx % VI_QN];
        d->used_idx++;
        struct vi_event ev = d->ev[e.id % VI_QN];
        vi_handle_event(d, &ev);
        d->avail->ring[d->avail_idx % VI_QN] = (unsigned short)(e.id % VI_QN);
        __asm__ volatile("dmb sy" ::: "memory");
        d->avail_idx++;
        d->avail->idx = d->avail_idx;
        kicked = 1;
    }
    if (kicked) r[0x50 / 4] = 0; /* QueueNotify */
}

static void vi_init_one(unsigned long base) {
    volatile unsigned int *r = (volatile unsigned int *)base;
    if (r[0] != 0x74726976) return;      /* MagicValue "virt" */
    if (r[0x08 / 4] != 18) return;       /* DeviceID: input */
    if (vi_count >= 2) return;
    struct vi_dev *d = &vi_devs[vi_count];
    d->r = r;
    d->version = (int)r[0x04 / 4];
    d->is_tablet = 0;
    d->is_keyboard = 0;
    r[0x70 / 4] = 0; /* Status: reset */
    for (int i = 0; i < 100000 && r[0x70 / 4] != 0; i++) { }
    r[0x70 / 4] = 1; /* ACKNOWLEDGE */
    r[0x70 / 4] |= 2; /* DRIVER */
    if (d->version >= 2) {
        r[0x24 / 4] = 0; r[0x20 / 4] = 0; /* DriverFeatures word 0: none */
        r[0x24 / 4] = 1; r[0x20 / 4] = 1; /* word 1: VIRTIO_F_VERSION_1 */
        r[0x70 / 4] |= 8; /* FEATURES_OK */
        if (!(r[0x70 / 4] & 8)) { uart_puts("virtio-input: features rejected\n"); return; }
    }
    if (vi_setup_queue(d, vq_mem[vi_count]) != 0) {
        uart_puts("virtio-input: no event queue\n");
        return;
    }
    r[0x70 / 4] |= 4; /* DRIVER_OK */
    r[0x50 / 4] = 0;  /* kick eventq */
    char name[64];
    vi_read_name(d, name, sizeof(name));
    d->is_tablet = str_contains(name, "Tablet");
    d->is_keyboard = str_contains(name, "Keyboard");
    if (!d->is_tablet && !d->is_keyboard) {
        int mn, mx;
        vi_abs_info(d, 0, &mn, &mx);
        if (mx > 0) d->is_tablet = 1; else d->is_keyboard = 1;
    }
    if (d->is_tablet) {
        vi_abs_info(d, 0, &d->abs_min_x, &d->abs_max_x);
        vi_abs_info(d, 1, &d->abs_min_y, &d->abs_max_y);
        if (d->abs_max_x <= d->abs_min_x) { d->abs_min_x = 0; d->abs_max_x = 32767; }
        if (d->abs_max_y <= d->abs_min_y) { d->abs_min_y = 0; d->abs_max_y = 32767; }
    }
    uart_puts("virtio-input: ");
    uart_puts(name[0] ? name : "(unnamed)");
    uart_puts(d->is_tablet ? " [tablet]\n" : " [keyboard]\n");
    vi_count++;
}
static void vi_init(void) {
    /* QEMU virt: 32 virtio-mmio transports at 0x0a000000 + 0x200*i
       (0x200-byte windows, region ends at 0x0a004000; probing past it
       takes a synchronous external abort). Devices fill from the top
       slot down, so scan them all and match DeviceID 18 (input). */
    for (int i = 0; i < 32; i++)
        vi_init_one(0x0a000000UL + 0x200UL * (unsigned long)i);
    if (vi_count == 0) uart_puts("virtio-input: none (UART input only)\n");
}

/* --- milestone 8.2: virtio-gpu display (tried first; ramfb is fallback) ---
   Minimal 2D path over the control virtqueue: create a 1024x768 resource
   backed by the same static fb[] the ramfb path uses, bind it to scanout 0,
   and push pixels with TRANSFER_TO_HOST_2D + RESOURCE_FLUSH after redraws.
   Same virtio-mmio transport handling as the input driver above (legacy
   QueuePFN and modern address+QueueReady paths). Commands are synchronous:
   one descriptor chain (request + writable response), polled to completion. */
#define GPU_QN 16
#define GPU_CMD_GET_DISPLAY_INFO 0x0100
#define GPU_CMD_RESOURCE_CREATE_2D 0x0101
#define GPU_CMD_SET_SCANOUT 0x0103
#define GPU_CMD_RESOURCE_FLUSH 0x0104
#define GPU_CMD_TRANSFER_TO_HOST_2D 0x0105
#define GPU_CMD_RESOURCE_ATTACH_BACKING 0x0106
#define GPU_RESP_OK_NODATA 0x1100
#define GPU_RESP_OK_DISPLAY_INFO 0x1101
#define GPU_FORMAT_B8G8R8X8 2 /* memory bytes B,G,R,X == our XRGB8888 words */

struct gpu_hdr { unsigned int type, flags; unsigned long long fence; unsigned int ctx, pad; };
static unsigned char gpu_qmem[8192] __attribute__((aligned(4096)));
static unsigned char gpu_req[64] __attribute__((aligned(16)));
static unsigned char gpu_resp[512] __attribute__((aligned(16)));
static volatile unsigned int *gpu_r = 0;
static struct vring_desc *gpu_desc;
static struct vring_avail *gpu_avail;
static struct vring_used *gpu_used;
static unsigned short gpu_avail_idx = 0, gpu_used_idx = 0;
static int gpu_active = 0;

static void gpu_put32(unsigned int off, unsigned int v) { *(unsigned int *)(gpu_req + off) = v; }
static void gpu_put64(unsigned int off, unsigned long long v) { *(unsigned long long *)(gpu_req + off) = v; }
static unsigned int gpu_resp32(unsigned int off) { return *(unsigned int *)(gpu_resp + off); }

/* Run one control command. The caller fills the request body at gpu_req+24;
   req_extra is the body length. Returns the response type, or -1 on timeout. */
static int gpu_cmd(unsigned int type, unsigned int req_extra, unsigned int resp_len) {
    for (unsigned int i = 0; i < sizeof(gpu_resp); i++) gpu_resp[i] = 0;
    struct gpu_hdr *h = (struct gpu_hdr *)gpu_req;
    h->type = type; h->flags = 0; h->fence = 0; h->ctx = 0; h->pad = 0;
    gpu_desc[0].addr = (unsigned long)gpu_req;
    gpu_desc[0].len = 24 + req_extra;
    gpu_desc[0].flags = 1; /* NEXT */
    gpu_desc[0].next = 1;
    gpu_desc[1].addr = (unsigned long)gpu_resp;
    gpu_desc[1].len = resp_len;
    gpu_desc[1].flags = 2; /* WRITE */
    gpu_desc[1].next = 0;
    gpu_avail->ring[gpu_avail_idx % GPU_QN] = 0;
    __asm__ volatile("dmb sy" ::: "memory");
    gpu_avail_idx++;
    gpu_avail->idx = gpu_avail_idx;
    gpu_r[0x50 / 4] = 0; /* QueueNotify: controlq */
    long spin = 0;
    for (;;) {
        __asm__ volatile("dmb sy" ::: "memory");
        if (gpu_used->idx != gpu_used_idx) break;
        if (++spin > 500000000L) return -1; /* device not answering */
    }
    gpu_used_idx++;
    unsigned int isr = gpu_r[0x60 / 4]; /* InterruptStatus */
    if (isr) gpu_r[0x64 / 4] = isr;    /* InterruptACK */
    return (int)((struct gpu_hdr *)gpu_resp)->type;
}

static int gpu_setup_queue(int version) {
    volatile unsigned int *r = gpu_r;
    r[0x30 / 4] = 0; /* QueueSel: controlq */
    if (r[0x34 / 4] == 0) return -1; /* QueueNumMax */
    r[0x38 / 4] = GPU_QN; /* QueueNum */
    unsigned int align = (version == 1) ? r[0x3C / 4] : 4096; /* QueueAlign */
    if (align == 0) align = 4096;
    unsigned int avail_off = GPU_QN * 16;
    unsigned int used_off = avail_off + 6 + 2 * GPU_QN;
    used_off = (used_off + align - 1) & ~(align - 1);
    gpu_desc = (struct vring_desc *)gpu_qmem;
    gpu_avail = (struct vring_avail *)(gpu_qmem + avail_off);
    gpu_used = (struct vring_used *)(gpu_qmem + used_off);
    gpu_avail->flags = 0; gpu_avail->idx = 0;
    gpu_used->flags = 0; gpu_used->idx = 0;
    gpu_avail_idx = 0; gpu_used_idx = 0;
    __asm__ volatile("dmb sy" ::: "memory");
    if (version == 1) {
        r[0x28 / 4] = 4096; /* GuestPageSize first, as for the input driver */
        r[0x40 / 4] = (unsigned int)((unsigned long)gpu_qmem / 4096); /* QueuePFN */
    } else {
        unsigned long m = (unsigned long)gpu_qmem;
        unsigned long a = (unsigned long)gpu_avail, u = (unsigned long)gpu_used;
        r[0x80 / 4] = (unsigned int)m;         r[0x84 / 4] = (unsigned int)(m >> 32);
        r[0x90 / 4] = (unsigned int)a;         r[0x94 / 4] = (unsigned int)(a >> 32);
        r[0xA0 / 4] = (unsigned int)u;         r[0xA4 / 4] = (unsigned int)(u >> 32);
        r[0x44 / 4] = 1; /* QueueReady */
    }
    return 0;
}

static int gpu_init_one(unsigned long base) {
    volatile unsigned int *r = (volatile unsigned int *)base;
    if (r[0] != 0x74726976) return -1;   /* MagicValue "virt" */
    if (r[0x08 / 4] != 16) return -1;    /* DeviceID: GPU */
    gpu_r = r;
    int version = (int)r[0x04 / 4];
    r[0x70 / 4] = 0; /* Status: reset */
    for (int i = 0; i < 100000 && r[0x70 / 4] != 0; i++) { }
    r[0x70 / 4] = 1; /* ACKNOWLEDGE */
    r[0x70 / 4] |= 2; /* DRIVER */
    if (version >= 2) {
        r[0x24 / 4] = 0; r[0x20 / 4] = 0; /* device features: none (no virgl/edid) */
        r[0x24 / 4] = 1; r[0x20 / 4] = 1; /* word 1: VIRTIO_F_VERSION_1 */
        r[0x70 / 4] |= 8; /* FEATURES_OK */
        if (!(r[0x70 / 4] & 8)) { uart_puts("virtio-gpu: features rejected\n"); return -1; }
    }
    if (gpu_setup_queue(version) != 0) { uart_puts("virtio-gpu: no control queue\n"); return -1; }
    r[0x70 / 4] |= 4; /* DRIVER_OK */
    int t = gpu_cmd(GPU_CMD_GET_DISPLAY_INFO, 0, 24 + 16 * 24);
    if (t != GPU_RESP_OK_DISPLAY_INFO) { uart_puts("virtio-gpu: no display info\n"); return -1; }
    uart_puts("virtio-gpu: scanout ");
    uart_putnum(gpu_resp32(24 + 8)); /* pmodes[0].r.width */
    uart_putc('x');
    uart_putnum(gpu_resp32(24 + 12)); /* pmodes[0].r.height */
    uart_puts(gpu_resp32(24 + 16) ? " enabled\n" : " (reported disabled)\n");
    /* RESOURCE_CREATE_2D: resource_id, format, width, height */
    gpu_put32(24, 1); gpu_put32(28, GPU_FORMAT_B8G8R8X8);
    gpu_put32(32, FB_W); gpu_put32(36, FB_H);
    t = gpu_cmd(GPU_CMD_RESOURCE_CREATE_2D, 16, 24);
    if (t != GPU_RESP_OK_NODATA) { uart_puts("virtio-gpu: create2d failed\n"); return -1; }
    /* RESOURCE_ATTACH_BACKING: resource_id, nr_entries, {addr, len, pad} */
    gpu_put32(24, 1); gpu_put32(28, 1);
    gpu_put64(32, (unsigned long)fb);
    gpu_put32(40, FB_W * FB_H * 4); gpu_put32(44, 0);
    t = gpu_cmd(GPU_CMD_RESOURCE_ATTACH_BACKING, 24, 24);
    if (t != GPU_RESP_OK_NODATA) { uart_puts("virtio-gpu: attach backing failed\n"); return -1; }
    /* SET_SCANOUT: rect, scanout_id, resource_id */
    gpu_put32(24, 0); gpu_put32(28, 0); gpu_put32(32, FB_W); gpu_put32(36, FB_H);
    gpu_put32(40, 0); gpu_put32(44, 1);
    t = gpu_cmd(GPU_CMD_SET_SCANOUT, 24, 24);
    if (t != GPU_RESP_OK_NODATA) { uart_puts("virtio-gpu: set scanout failed\n"); return -1; }
    gpu_active = 1;
    return 0;
}

static void gpu_flush(void) {
    if (!gpu_active) return;
    /* TRANSFER_TO_HOST_2D: rect, offset, resource_id, pad */
    gpu_put32(24, 0); gpu_put32(28, 0); gpu_put32(32, FB_W); gpu_put32(36, FB_H);
    gpu_put64(40, 0);
    gpu_put32(48, 1); gpu_put32(52, 0);
    gpu_cmd(GPU_CMD_TRANSFER_TO_HOST_2D, 32, 24);
    /* RESOURCE_FLUSH: rect, resource_id, pad */
    gpu_put32(24, 0); gpu_put32(28, 0); gpu_put32(32, FB_W); gpu_put32(36, FB_H);
    gpu_put32(40, 1); gpu_put32(44, 0);
    gpu_cmd(GPU_CMD_RESOURCE_FLUSH, 24, 24);
}

static void disp_flush(void) { if (gpu_active) gpu_flush(); }

/* Display selection: virtio-gpu first (what Vectras shows), ramfb fallback
   (the desktop-QEMU setup used through stage 8.1). */
static void display_init(void) {
    for (int i = 0; i < 32; i++) {
        if (gpu_init_one(0x0a000000UL + 0x200UL * (unsigned long)i) == 0) {
            fb_ready = 1;
            uart_puts("display: virtio-gpu\n");
            return;
        }
    }
    uart_puts("virtio-gpu: none\n");
    screen_init();
    if (fb_ready) uart_puts("display: ramfb\n");
}

/* --- GUI main loop --- */
static void fs_seed(void) {
    static const char *seed[2][2] = {
        {"hello.txt", "Hello from the NeoOS GUI!"},
        {"about.txt", "NeoOS stage 8: windows, mouse, apps"}
    };
    for (int i = 0; i < 2; i++) {
        int idx = fs_create(seed[i][0]);
        if (idx >= 0) {
            const char *s = seed[i][1];
            while (*s) fs_append_byte(idx, *s++);
        }
    }
}

static void gui_main(void) {
    vi_init();
    wm_init();
    term_clear();
    term_puts("NeoOS shell. Type 'help'.\n");
    term_puts("neo> ");
    fs_seed();
    gui_dirty = 1;
    unsigned long last_tick = ticks;
    uart_puts("gui on (UART ESC returns to serial shell)\n");
    while (1) {
        for (int i = 0; i < vi_count; i++) vi_poll(&vi_devs[i]);
        while (!(UART0[6] & 0x10)) { /* RXFE clear: byte waiting */
            char c = (char)(UART0[0] & 0xFF);
            if (c == 0x1B) { uart_puts("\ngui off\n"); return; }
            inq_push(c == '\r' ? '\n' : c);
        }
        int c;
        while ((c = inq_pop()) >= 0) {
            if (wins[zord[3]].kind == W_TERM) term_key((char)c);
        }
        if (ticks != last_tick) { last_tick = ticks; gui_dirty = 1; }
        if (gui_dirty) { wm_redraw(); disp_flush(); gui_dirty = 0; }
    }
}

/* ---------- main ---------- */
void kernel_main(void) {
    uart_puts("NeoOS kernel: boot ok\n");
    irq_init();
    uart_puts("timer on\n");
    mem_init();
    mem_selftest();
    sched_init();
    display_init();
    if (fb_ready) gui_main(); /* returns when UART ESC is pressed */
    draw_scene();
    shell();
}
