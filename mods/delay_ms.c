/* USB guard: hardware-mute the loudspeakers the moment the USB DAC reports "bus down",
 * and keep them muted until the bus has been back for 1.8 s.
 *
 * The factory firmware only looks at this pin every 30 ms and then ramps the DSP volume
 * down (about 85 ms time constant), so the DAC's suspend/resume transient gets through.
 * usb_guard() is called from the idle part of the main loop and from inside delay_ms(),
 * so it runs every few microseconds except during an I2C transfer.  The 10 kHz timer
 * interrupt is deliberately left alone: see kit/isr_budget.py.
 *
 * delay_ms() replaces the factory routine at 0x41cc; same timing, plus the guard call.
 */
#define REG32(a) (*(volatile unsigned *)(a))
#define REG8(a)  (*(volatile unsigned char *)(a))

#define PF4          REG32(0x40004950)  /* 0 = no USB 5 V. NOT the PCM2704 SSPND flag: it stays high when a
                                           self-powered hub switches hosts (see AGENTS.md), so this guard
                                           only fires on cable removal or hubs that cut the 5 V */
#define PA3          REG32(0x4000480C)  /* 0 = plug in the headphone jack (inferred from behaviour) */
#define PC0          REG32(0x40004880)  /* 1 = loudspeakers muted */
#define TICK         REG32(0x200000ec)  /* 100 us ticks from TMR0_IRQHandler */
#define POWER_STATE  REG8(0x200000c4)   /* 2 = running */
#define INPUT        REG8(0x200000dc)   /* 1 = USB */
#define FADEIN_DONE  REG8(0x20000054)
#define GUARD        REG32(0x20000328)  /* new variable: tick of the last "bus down" sighting, 0 = idle.
                                           First word above the factory RAM; zeroed at start-up by the
                                           lengthened zero-init region in mods/usb-guard.patch. */
#define HOLD_TICKS   18000              /* 1.8 s: ends before the firmware's own 2 s volume restore */

void usb_guard(void)
{
    unsigned since = GUARD;
    unsigned now = TICK | 1;            /* never 0, so 0 can mean "idle" */

    if (INPUT == 1) {
        if (PF4 == 0) {
            PC0 = 1;
            GUARD = now;
            return;
        }
        if (since && now - since < HOLD_TICKS) {
            PC0 = 1;
            return;
        }
    }
    if (since) {
        GUARD = 0;
        /* hand the pin back in the state the factory code would have it in */
        PC0 = !(POWER_STATE == 2 && PA3 != 0 && FADEIN_DONE != 0);
    }
}

void delay_ms(unsigned ms)
{
    unsigned start = TICK;

    while (TICK - start < ms * 10)
        usb_guard();
}
