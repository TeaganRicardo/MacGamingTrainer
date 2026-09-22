from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ROOT / "Native/ProcessTimeWarp"

program = r"""
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include "TimeWarpMath.h"

static int expect_close(double actual, double expected) {
    return fabs(actual - expected) <= 0.000001;
}

int main(void) {
    if (!expect_close(mgt_time_warp_elapsed_ticks(125, 100), 25.0)) return 1;
    if (!expect_close(mgt_time_warp_elapsed_ticks(75, 100), -25.0)) return 2;
    if (!expect_close(mgt_time_warp_elapsed_ticks(100, 100), 0.0)) return 3;

    // This is the D01 race shape: a clock sample was captured before another
    // thread moved the speed anchor forward. The elapsed interval must remain
    // a small negative value, never uint64 underflow into a huge positive one.
    double stale = mgt_time_warp_elapsed_ticks(1000, 1001);
    if (!expect_close(stale, -1.0)) return 4;
    if (!isfinite(stale) || stale > 0.0) return 5;

    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mgt-time-warp-math-") as td:
    root = Path(td)
    source = root / "main.c"
    binary = root / "time-warp-math"
    source.write_text(program)
    subprocess.run([
        "cc",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(INCLUDE),
        str(source),
        "-lm",
        "-o",
        str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)

print("process_time_warp_native_math_ok")
