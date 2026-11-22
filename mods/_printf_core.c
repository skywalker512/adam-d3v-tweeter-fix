/* USB listen probe: can the MCU's own USB receiver see the bus while the speaker runs normally?
 *
 * Lives in the space of _printf_core (0x3df8..0x40cc), which only the HardFault report used, so the
 * image keeps its 22124 bytes and no other code moves (build with --keep-size).  The HardFault
 * handler still runs but prints nothing.
 *
 * gpio_init_probe() replaces the call to gpio_init() in main (mods/usb-probe.patch).  For the first
 * ~10 s after power-on it turns the USBD block on in listen-only mode (transceiver and controller on,
 * D+ pull-up OFF, SE0 drive OFF) and watches the frame number of the last received start-of-frame:
 *     LED blinks fast (5 per second): frame number is advancing, the MCU hears the host's 1 ms heartbeat
 *     LED blinks slow (1 per second): it does not
 * Then everything it touched is put back and the factory start-up continues unchanged.
 *
 * Register facts: OpenNuvoton/M031BSP usbd_reg.h, clk_reg.h, usbd.h (USBD_ENABLE_USB = 0x7D0).
 */
#define REG32(a) (*(volatile unsigned *)(a))

#define CLK_APBCLK0  REG32(0x40000208)  /* bit 27 = USBDCKEN */
#define USBD_ATTR    REG32(0x400C0010)  /* 0x6D0 = BYTEM | PWRDN | USBEN | bit 6 | PHYEN, without DPPUEN (bit 8) */
#define USBD_FN      REG32(0x400C008C)  /* frame number of the last SOF */
#define USBD_SE0     REG32(0x400C0090)  /* 1 = transceiver drives both lines low */
#define PB12         REG32(0x40004870)  /* the three LED pins */
#define PB13         REG32(0x40004874)
#define PB14         REG32(0x40004878)
#define TICK         REG32(0x200000ec)  /* 100 us ticks from TMR0_IRQHandler */

void gpio_init(void);

int _printf_core(void)
{
    return 0;
}

void gpio_init_probe(void)
{
    unsigned clk, se0, attr, led12, led13, led14, last, level = 0, slow = 0, slot;

    gpio_init();
    clk = CLK_APBCLK0; led12 = PB12; led13 = PB13; led14 = PB14;
    CLK_APBCLK0 = clk | 1u << 27;
    se0 = USBD_SE0; attr = USBD_ATTR;
    USBD_SE0 = 0;                       /* before the transceiver is enabled, so it never drives the lines */
    USBD_ATTR = 0x6D0;
    last = USBD_FN;

    for (slot = 0; slot < 100; slot++) {                    /* 100 x 100 ms */
        unsigned start = TICK, heard = 0, guard = 0;
        while (TICK - start < 1000 && ++guard < 4000000) {  /* guard: ends even if the tick never runs */
            unsigned fn = USBD_FN;
            if (fn != last) {
                last = fn;
                heard++;
            }
        }
        if (heard >= 8 || ++slow >= 5) {                    /* a live bus gives ~100 new frame numbers per slot */
            slow = 0;
            level ^= 1;
        }
        PB12 = level; PB13 = level; PB14 = level;
    }

    USBD_ATTR = attr; USBD_SE0 = se0; CLK_APBCLK0 = clk;
    PB12 = led12; PB13 = led13; PB14 = led14;
}
