#include <QuartzCore/CABase.h>
#include <mach/mach_time.h>
#include <mach-o/dyld.h>
#include <math.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#include "fishhook.h"
#include "TimeWarpMath.h"

#define MGT_EXPORT __attribute__((visibility("default")))
#define MGT_TIME_WARP_ABI 1u
#define MGT_MIN_SPEED 0.0
#define MGT_MAX_SPEED 10.0
#define MGT_IMAGE_FILTER_CAPACITY 1024u

enum {
    MGT_HOOK_MACH_ABSOLUTE = 1u << 0,
    MGT_HOOK_MACH_CONTINUOUS = 1u << 1,
    MGT_HOOK_CLOCK_GETTIME = 1u << 2,
    MGT_HOOK_CA_MEDIA_TIME = 1u << 3,
};

static _Atomic uint64_t sequence = 0;
static _Atomic uint64_t anchor_real_ticks = 0;
static _Atomic double anchor_offset_ticks = 0.0;
static _Atomic double trainer_speed = 1.0;
static _Atomic uint32_t hook_mask = 0;
static atomic_flag speed_lock = ATOMIC_FLAG_INIT;
static _Atomic bool installed = false;
static _Atomic bool callback_registered = false;

static mach_timebase_info_data_t timebase = {0, 0};
static char image_filter[MGT_IMAGE_FILTER_CAPACITY];
static size_t image_filter_length = 0;

static void *original_mach_absolute = NULL;
static void *original_mach_continuous = NULL;
static void *original_clock_gettime = NULL;
static void *original_ca_media_time = NULL;

static void lock_speed(void) {
    while (atomic_flag_test_and_set_explicit(&speed_lock, memory_order_acquire)) {}
}

static void unlock_speed(void) {
    atomic_flag_clear_explicit(&speed_lock, memory_order_release);
}

static bool valid_speed(double speed) {
    return isfinite(speed) && speed >= MGT_MIN_SPEED && speed <= MGT_MAX_SPEED;
}

static double offset_ticks_at(uint64_t real_now) {
    for (;;) {
        uint64_t before = atomic_load_explicit(&sequence, memory_order_acquire);
        if (before & 1u) continue;
        uint64_t anchor = atomic_load_explicit(&anchor_real_ticks, memory_order_relaxed);
        double offset = atomic_load_explicit(&anchor_offset_ticks, memory_order_relaxed);
        double speed = atomic_load_explicit(&trainer_speed, memory_order_relaxed);
        uint64_t after = atomic_load_explicit(&sequence, memory_order_acquire);
        if (before == after) {
            return offset + mgt_time_warp_elapsed_ticks(real_now, anchor) * (speed - 1.0);
        }
    }
}

static uint64_t apply_tick_offset(uint64_t real_value, double offset) {
    long double value = (long double)real_value + (long double)offset;
    if (value <= 0.0L) return 0;
    if (value >= (long double)UINT64_MAX) return UINT64_MAX;
    return (uint64_t)llroundl(value);
}

static double ticks_to_seconds(double ticks) {
    return ticks * (double)timebase.numer / (double)timebase.denom / 1000000000.0;
}

static int set_speed_continuous(double speed) {
    if (!valid_speed(speed)) return -1;
    lock_speed();
    atomic_fetch_add_explicit(&sequence, 1, memory_order_acq_rel);
    uint64_t now = mach_absolute_time();
    uint64_t anchor = atomic_load_explicit(&anchor_real_ticks, memory_order_relaxed);
    double offset = atomic_load_explicit(&anchor_offset_ticks, memory_order_relaxed);
    double previous = atomic_load_explicit(&trainer_speed, memory_order_relaxed);
    if (anchor != 0) {
        offset += (double)(now - anchor) * (previous - 1.0);
    }
    atomic_store_explicit(&anchor_real_ticks, now, memory_order_relaxed);
    atomic_store_explicit(&anchor_offset_ticks, offset, memory_order_relaxed);
    atomic_store_explicit(&trainer_speed, speed, memory_order_relaxed);
    atomic_fetch_add_explicit(&sequence, 1, memory_order_release);
    unlock_speed();
    return 0;
}

static uint64_t warped_mach_absolute_time(void) {
    uint64_t real = mach_absolute_time();
    return apply_tick_offset(real, offset_ticks_at(real));
}

static uint64_t warped_mach_continuous_time(void) {
    uint64_t reference = mach_absolute_time();
    uint64_t real = mach_continuous_time();
    return apply_tick_offset(real, offset_ticks_at(reference));
}

static bool should_warp_clock(clockid_t clock_id) {
    if (clock_id == CLOCK_MONOTONIC) return true;
#ifdef CLOCK_MONOTONIC_RAW
    if (clock_id == CLOCK_MONOTONIC_RAW) return true;
#endif
#ifdef CLOCK_MONOTONIC_RAW_APPROX
    if (clock_id == CLOCK_MONOTONIC_RAW_APPROX) return true;
#endif
#ifdef CLOCK_UPTIME_RAW
    if (clock_id == CLOCK_UPTIME_RAW) return true;
#endif
#ifdef CLOCK_UPTIME_RAW_APPROX
    if (clock_id == CLOCK_UPTIME_RAW_APPROX) return true;
#endif
    return false;
}

static int warped_clock_gettime(clockid_t clock_id, struct timespec *value) {
    int result = clock_gettime(clock_id, value);
    if (result != 0 || value == NULL || !should_warp_clock(clock_id)) return result;

    uint64_t reference = mach_absolute_time();
    double offset_seconds = ticks_to_seconds(offset_ticks_at(reference));
    long double seconds = (long double)value->tv_sec + (long double)value->tv_nsec / 1000000000.0L + offset_seconds;
    if (seconds < 0.0L) seconds = 0.0L;
    time_t whole = (time_t)floorl(seconds);
    long double fraction = seconds - (long double)whole;
    value->tv_sec = whole;
    value->tv_nsec = (long)llroundl(fraction * 1000000000.0L);
    if (value->tv_nsec >= 1000000000L) {
        value->tv_sec += 1;
        value->tv_nsec -= 1000000000L;
    }
    return result;
}

static CFTimeInterval warped_ca_current_media_time(void) {
    uint64_t reference = mach_absolute_time();
    return CACurrentMediaTime() + ticks_to_seconds(offset_ticks_at(reference));
}

static const char *image_basename(const char *path) {
    if (path == NULL) return "";
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

static bool selected_image_name(const char *path) {
    const char *name = image_basename(path);
    const char *cursor = image_filter;
    const char *limit = image_filter + image_filter_length;
    while (cursor < limit) {
        const char *newline = memchr(cursor, '\n', (size_t)(limit - cursor));
        const char *end = newline ? newline : limit;
        size_t length = (size_t)(end - cursor);
        if (length == strlen(name) && memcmp(cursor, name, length) == 0) return true;
        cursor = newline ? newline + 1 : limit;
    }
    return false;
}

static const char *path_for_header(const struct mach_header *header) {
    uint32_t count = _dyld_image_count();
    for (uint32_t index = 0; index < count; index++) {
        if (_dyld_get_image_header(index) == header) return _dyld_get_image_name(index);
    }
    return NULL;
}

static void rebind_selected_image(const struct mach_header *header, intptr_t slide) {
    const char *path = path_for_header(header);
    if (!selected_image_name(path)) return;

    struct rebinding bindings[] = {
        {"mach_absolute_time", (void *)warped_mach_absolute_time, &original_mach_absolute},
        {"mach_continuous_time", (void *)warped_mach_continuous_time, &original_mach_continuous},
        {"clock_gettime", (void *)warped_clock_gettime, &original_clock_gettime},
        {"CACurrentMediaTime", (void *)warped_ca_current_media_time, &original_ca_media_time},
    };
    if (rebind_symbols_image((void *)header, slide, bindings, sizeof(bindings) / sizeof(bindings[0])) != 0) {
        return;
    }

    uint32_t discovered = 0;
    if (original_mach_absolute != NULL) discovered |= MGT_HOOK_MACH_ABSOLUTE;
    if (original_mach_continuous != NULL) discovered |= MGT_HOOK_MACH_CONTINUOUS;
    if (original_clock_gettime != NULL) discovered |= MGT_HOOK_CLOCK_GETTIME;
    if (original_ca_media_time != NULL) discovered |= MGT_HOOK_CA_MEDIA_TIME;
    atomic_fetch_or_explicit(&hook_mask, discovered, memory_order_release);
}

MGT_EXPORT uint32_t MGTTimeWarpABI(void) {
    return MGT_TIME_WARP_ABI;
}

MGT_EXPORT uint32_t MGTTimeWarpHookMask(void) {
    return atomic_load_explicit(&hook_mask, memory_order_acquire);
}

MGT_EXPORT double MGTTimeWarpGetSpeed(void) {
    return atomic_load_explicit(&trainer_speed, memory_order_acquire);
}

MGT_EXPORT int MGTTimeWarpInstall(const char *image_names, size_t length, double speed) {
    if (image_names == NULL || length == 0 || length >= MGT_IMAGE_FILTER_CAPACITY) return -2;
    if (!valid_speed(speed)) return -1;

    if (atomic_load_explicit(&installed, memory_order_acquire)) {
        if (length != image_filter_length || memcmp(image_names, image_filter, length) != 0) return -4;
        if (atomic_load_explicit(&hook_mask, memory_order_acquire) == 0) return -3;
        return set_speed_continuous(speed);
    }

    memcpy(image_filter, image_names, length);
    image_filter[length] = '\0';
    image_filter_length = length;
    if (mach_timebase_info(&timebase) != KERN_SUCCESS || timebase.numer == 0 || timebase.denom == 0) return -5;
    if (set_speed_continuous(speed) != 0) return -1;

    atomic_store_explicit(&installed, true, memory_order_release);
    bool was_registered = atomic_exchange_explicit(&callback_registered, true, memory_order_acq_rel);
    if (!was_registered) {
        _dyld_register_func_for_add_image(rebind_selected_image);
    } else {
        // A previous attempt registered the persistent callback but found no
        // matching hooks. Re-scan images already loaded with the new filter;
        // the existing callback continues to cover future images. Do not
        // register another callback (dyld has no unregister API).
        uint32_t count = _dyld_image_count();
        for (uint32_t index = 0; index < count; index++) {
            rebind_selected_image(_dyld_get_image_header(index), _dyld_get_image_vmaddr_slide(index));
        }
    }

    if (atomic_load_explicit(&hook_mask, memory_order_acquire) == 0) {
        set_speed_continuous(1.0);
        // R-02: roll back installed/filter state so a corrected retry can
        // update the filter and re-scan loaded images. Keep the one registered
        // callback: it handles future images and must not be duplicated.
        atomic_store_explicit(&installed, false, memory_order_release);
        image_filter_length = 0;
        return -3;
    }
    return 0;
}

MGT_EXPORT int MGTTimeWarpSetSpeed(double speed) {
    if (!atomic_load_explicit(&installed, memory_order_acquire)) return -6;
    if (atomic_load_explicit(&hook_mask, memory_order_acquire) == 0) return -3;
    return set_speed_continuous(speed);
}
