// Bounded native function CPU probe. Stub clocks/binding are explicit; no game.
#include <stdio.h>
#include <stdlib.h>
#include "ProcessTimeWarp.c"
static volatile uint64_t ticks = 1000000;
static struct mach_header header;
static volatile uint64_t sink;
kern_return_t mach_timebase_info(mach_timebase_info_data_t *info) {
    info->numer = 1; info->denom = 1; return KERN_SUCCESS;
}
uint64_t mach_absolute_time(void) { return ++ticks; }
uint64_t mach_continuous_time(void) { return ++ticks; }
CFTimeInterval CACurrentMediaTime(void) { return 1.0; }
uint32_t _dyld_image_count(void) { return 1; }
const struct mach_header *_dyld_get_image_header(uint32_t i) { return i == 0 ? &header : NULL; }
const char *_dyld_get_image_name(uint32_t i) { return i == 0 ? "/fixture/ProfileClock" : NULL; }
intptr_t _dyld_get_image_vmaddr_slide(uint32_t i) { (void)i; return 0; }
void _dyld_register_func_for_add_image(mgt_image_callback callback) { callback(&header, 0); }
int rebind_symbols_image(void *h, intptr_t slide, struct rebinding bindings[], size_t count) {
    (void)h; (void)slide;
    for (size_t i = 0; i < count; i++) if (bindings[i].replaced) *bindings[i].replaced = &header;
    return 0;
}
static void measure(const char *label, int samples, uint64_t (*read_clock)(void)) {
    for (int sample = 0; sample < samples + 3; sample++) {
        clock_t started = clock();
        for (int i = 0; i < 100000; i++) sink = read_clock();
        double seconds = (double)(clock() - started) / CLOCKS_PER_SEC / 100000;
        if (sample >= 3) printf("%s\t%.12f\n", label, seconds);
    }
}
int main(int argc, char **argv) {
    if (argc != 2) return 1;
    int samples = atoi(argv[1]);
    if (samples < 1 || samples > 1000) return 2;
    measure("never_enabled", samples, mach_absolute_time);
    if (MGTTimeWarpInstall("ProfileClock", 12, 2.0) || !MGTTimeWarpHookMask()) return 3;
    if (MGTTimeWarpGetSpeed() != 2.0) return 4;
    measure("active_2x", samples, warped_mach_absolute_time);
    if (MGTTimeWarpSetSpeed(1.0) || MGTTimeWarpGetSpeed() != 1.0) return 5;
    measure("enabled_then_reset_1x", samples, warped_mach_absolute_time);
    return sink == 0 ? 6 : 0;
}
