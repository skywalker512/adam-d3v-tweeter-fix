/* C replacement for the factory routine at 0x28f0: 12-bit ADC reading of a rear-panel
 * switch -> position index.  Readings in the two gaps (1000..1500, 2500..3000) return the
 * raw value, exactly as the factory code does. */
unsigned adc_to_switch3(unsigned v)
{
    if (v > 3000)
        return 0;
    if (v > 1500 && v < 2500)
        return 1;
    if (v < 1000)
        return 2;
    return v;
}
