import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "Native/ProcessTimeWarp"

stubs = {
    "QuartzCore/CABase.h": r"""
#pragma once
typedef double CFTimeInterval;
CFTimeInterval CACurrentMediaTime(void);
""",
    "mach/mach_time.h": r"""
#pragma once
#include <stdint.h>
typedef int kern_return_t;
typedef struct { uint32_t numer, denom; } mach_timebase_info_data_t;
enum { KERN_SUCCESS = 0 };
kern_return_t mach_timebase_info(mach_timebase_info_data_t *info);
uint64_t mach_absolute_time(void);
uint64_t mach_continuous_time(void);
""",
    "mach-o/dyld.h": r"""
#pragma once
#include <stdint.h>
struct mach_header { uint32_t magic; };
typedef void (*mgt_image_callback)(const struct mach_header *, intptr_t);
uint32_t _dyld_image_count(void);
const struct mach_header *_dyld_get_image_header(uint32_t index);
const char *_dyld_get_image_name(uint32_t index);
void _dyld_register_func_for_add_image(mgt_image_callback callback);
""",
}

harness = r"""
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "ProcessTimeWarp.c"

#define THREAD_COUNT 24
static _Atomic unsigned timebase_calls;
static _Atomic unsigned register_calls;
static _Atomic unsigned selected_rebinds;
static _Atomic uint64_t ticks = 1000;
static struct mach_header headers[2];
static int original_marker;

kern_return_t mach_timebase_info(mach_timebase_info_data_t *info) {
    atomic_fetch_add_explicit(&timebase_calls, 1, memory_order_relaxed);
    struct timespec pause = {0, 30000000};
    nanosleep(&pause, NULL);
    info->numer = 1;
    info->denom = 1;
    return KERN_SUCCESS;
}

uint64_t mach_absolute_time(void) {
    return atomic_fetch_add_explicit(&ticks, 1, memory_order_relaxed);
}
uint64_t mach_continuous_time(void) { return mach_absolute_time(); }
CFTimeInterval CACurrentMediaTime(void) { return 1.0; }
uint32_t _dyld_image_count(void) { return 2; }
const struct mach_header *_dyld_get_image_header(uint32_t index) {
    return index < 2 ? &headers[index] : NULL;
}
const char *_dyld_get_image_name(uint32_t index) {
    return index == 0 ? "/fixture/TargetA" : index == 1 ? "/fixture/TargetB" : NULL;
}
void _dyld_register_func_for_add_image(mgt_image_callback callback) {
    atomic_fetch_add_explicit(&register_calls, 1, memory_order_relaxed);
    // Darwin invokes a newly registered add-image callback for loaded images
    // synchronously. This also detects callback paths that take install_lock.
    callback(&headers[0], 0);
    callback(&headers[1], 0);
}
int rebind_symbols_image(void *header, intptr_t slide, struct rebinding bindings[], size_t count) {
    (void)slide;
    (void)header;
    atomic_fetch_add_explicit(&selected_rebinds, 1, memory_order_relaxed);
    for (size_t i = 0; i < count; ++i) {
        if (bindings[i].replaced != NULL) *bindings[i].replaced = &original_marker;
    }
    return 0;
}

typedef struct {
    _Atomic unsigned *ready;
    _Atomic bool *go;
    const char *images;
    int result;
} install_job;

static void *run_install(void *opaque) {
    install_job *job = opaque;
    atomic_fetch_add_explicit(job->ready, 1, memory_order_release);
    while (!atomic_load_explicit(job->go, memory_order_acquire)) sched_yield();
    job->result = MGTTimeWarpInstall(job->images, strlen(job->images), 2.0);
    return NULL;
}

int main(void) {
    pthread_t threads[THREAD_COUNT];
    install_job jobs[THREAD_COUNT];
    _Atomic unsigned ready = 0;
    _Atomic bool go = false;
    unsigned successes = 0;
    unsigned mismatches = 0;

    for (unsigned i = 0; i < THREAD_COUNT; ++i) {
        jobs[i] = (install_job){&ready, &go, (i & 1) ? "TargetA" : "TargetB", -99};
        if (pthread_create(&threads[i], NULL, run_install, &jobs[i]) != 0) return 10;
    }
    while (atomic_load_explicit(&ready, memory_order_acquire) != THREAD_COUNT) sched_yield();
    atomic_store_explicit(&go, true, memory_order_release);
    for (unsigned i = 0; i < THREAD_COUNT; ++i) {
        if (pthread_join(threads[i], NULL) != 0) return 11;
        if (jobs[i].result == 0) ++successes;
        else if (jobs[i].result == -4) ++mismatches;
        else {
            fprintf(stderr, "unexpected install result: %d\n", jobs[i].result);
            return 12;
        }
    }
    {
        const char *installed_images = NULL;
        for (unsigned i = 0; i < THREAD_COUNT; ++i) {
            if (jobs[i].result == 0) {
                if (installed_images == NULL) installed_images = jobs[i].images;
                else if (strcmp(installed_images, jobs[i].images) != 0) {
                    fprintf(stderr, "different image filters both reported install success\n");
                    return 13;
                }
            }
        }
        if (successes == 0 || successes + mismatches != THREAD_COUNT) {
            fprintf(stderr, "install serialization: success=%u mismatch=%u\n", successes, mismatches);
            return 14;
        }
    }
    if (atomic_load_explicit(&timebase_calls, memory_order_relaxed) != 1) {
        fprintf(stderr, "timebase initialized %u times\n", atomic_load_explicit(&timebase_calls, memory_order_relaxed));
        return 15;
    }
    if (atomic_load_explicit(&register_calls, memory_order_relaxed) != 1) {
        fprintf(stderr, "dyld callback registered %u times\n", atomic_load_explicit(&register_calls, memory_order_relaxed));
        return 16;
    }
    if (MGTTimeWarpHookMask() == 0 || atomic_load_explicit(&selected_rebinds, memory_order_relaxed) != 1) {
        fprintf(stderr, "callback did not read the published matching image snapshot\n");
        return 17;
    }
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mgt-time-warp-install-") as td:
    temp = Path(td)
    for relative, content in stubs.items():
        header = temp / "stubs" / relative
        header.parent.mkdir(parents=True, exist_ok=True)
        header.write_text(content)
    harness_path = temp / "install_harness.c"
    binary = temp / "install_harness"
    harness_path.write_text(harness)
    subprocess.run([
        "cc", "-std=c11", "-D_DEFAULT_SOURCE", "-pthread", "-Wall", "-Wextra", "-Werror",
        "-I", str(temp / "stubs"), "-I", str(NATIVE), "-I", str(NATIVE / "vendor/fishhook"),
        str(harness_path), "-lm", "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True, timeout=10)

print("process_time_warp_install_contract_ok")
