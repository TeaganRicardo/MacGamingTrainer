#ifndef MGT_TIME_WARP_MATH_H
#define MGT_TIME_WARP_MATH_H

#include <stdint.h>

static inline double mgt_time_warp_elapsed_ticks(uint64_t sample, uint64_t anchor) {
    if (sample >= anchor) return (double)(sample - anchor);
    return -(double)(anchor - sample);
}

#endif
