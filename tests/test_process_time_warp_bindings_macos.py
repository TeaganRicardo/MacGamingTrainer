"""Real fishhook slot writes distinguish successful binding from protection failure."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'Native/ProcessTimeWarp/vendor/fishhook'

PROGRAM = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
static unsigned protect_calls;
static unsigned deny_call;
#define vm_protect fixture_vm_protect
#include "fishhook.c"
#undef vm_protect

kern_return_t fixture_vm_protect(vm_map_t task, vm_address_t address,
                                vm_size_t size, boolean_t maximum, vm_prot_t protection) {
    (void)task; (void)address; (void)size; (void)maximum; (void)protection;
    ++protect_calls;
    return deny_call == protect_calls || deny_call == 99 ? KERN_PROTECTION_FAILURE : KERN_SUCCESS;
}

int main(void) {
    int originals[2], replacements[2];
    char names[] = "\0_clock_gettime\0_mach_absolute_time\0";
    nlist_t symbols[2] = {{0}};
    symbols[0].n_un.n_strx = 1;
    symbols[1].n_un.n_strx = 2 + strlen(names + 1);
    uint32_t indirect[] = {0, 1};
    for (unsigned failure = 0; failure < 3; ++failure) {
        void *slots[] = {&originals[0], &originals[1]};
        void *saved[] = {NULL, NULL};
        struct rebinding_result results[2] = {{0}};
        struct rebinding bindings[] = {
            {"clock_gettime", &replacements[0], &saved[0], &results[0]},
            {"mach_absolute_time", &replacements[1], &saved[1], &results[1]},
        };
        struct rebindings_entry entry = {bindings, 2, NULL};
        section_t section = {0};
        section.addr = (uintptr_t)slots;
        section.size = sizeof(slots);
        protect_calls = 0;
        deny_call = failure == 0 ? 0 : failure == 1 ? 99 : 2;
        perform_rebinding_with_section(&entry, &section, 0, symbols, names, indirect);
        assert(protect_calls == 2);
        for (unsigned index = 0; index < 2; ++index) {
            bool denied = failure == 1 || (failure == 2 && index == 1);
            assert(saved[index] == &originals[index]);
            assert(slots[index] == (denied ? (void *)&originals[index] : (void *)&replacements[index]));
            assert(results[index].rebound == (denied ? 0u : 1u));
            assert(results[index].failed == (denied ? 1u : 0u));
        }
    }
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-fishhook-receipts-') as temporary:
    root = Path(temporary)
    source = root / 'main.c'
    binary = root / 'bindings'
    source.write_text(PROGRAM)
    subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-I', str(VENDOR), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=10)

print('process_time_warp_actual_binding_receipts_ok')
