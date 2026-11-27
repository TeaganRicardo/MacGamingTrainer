"""Real macOS universal (arm64 + x86_64) build & Rosetta 2 cross-arch mailbox test."""
MGT_PLATFORM = "macos"

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "Tools"))

from build_module_native import build_libraries
from games.hades.mailbox import HadesCommandMailbox
from games.hades.native_mailbox import CPU_TYPE_ARM64, CPU_TYPE_X86_64, slice_uuid

clang = shutil.which("clang") or subprocess.check_output(["xcrun", "--find", "clang"], text=True).strip()
clangxx = shutil.which("clang++") or subprocess.check_output(["xcrun", "--find", "clang++"], text=True).strip()
sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
manifest = json.loads((ROOT / "Backend/games/hades/module.json").read_text(encoding="utf-8"))

with tempfile.TemporaryDirectory(prefix="mgt-hades-rosetta-mailbox-") as temporary:
    tmp = Path(temporary)
    staging = tmp / "staging"
    out_dir = tmp / "out"
    staging.mkdir()
    build_libraries(
        manifest,
        ROOT / "Backend/games/hades",
        staging,
        clang=clang,
        sdk=sdk,
        architectures=["arm64", "x86_64"],
        minimum_macos="14.0",
        output_dir=out_dir,
    )
    dylib_path = out_dir / "libMGTHadesCommandMailbox.dylib"
    assert dylib_path.is_file()
    subprocess.run(["codesign", "--verify", "--strict", str(dylib_path)], check=True)
    subprocess.run(["xcrun", "lipo", str(dylib_path), "-verify_arch", "arm64"], check=True)
    subprocess.run(["xcrun", "lipo", str(dylib_path), "-verify_arch", "x86_64"], check=True)

    dwarfdump = subprocess.check_output(["xcrun", "dwarfdump", "--uuid", str(dylib_path)], text=True)
    expected_x86_uuid = None
    expected_arm_uuid = None
    for line in dwarfdump.splitlines():
        if "(x86_64)" in line:
            expected_x86_uuid = line.split()[1].replace("-", "").upper()
        elif "(arm64)" in line:
            expected_arm_uuid = line.split()[1].replace("-", "").upper()
    assert expected_x86_uuid and expected_arm_uuid and expected_x86_uuid != expected_arm_uuid
    assert slice_uuid(dylib_path, target_cputype=CPU_TYPE_X86_64) == expected_x86_uuid
    assert slice_uuid(dylib_path, target_cputype=CPU_TYPE_ARM64) == expected_arm_uuid

    # Build an x86_64 host binary simulating Hades's writable __DATA C++ vtable +
    # background allocation thread, dlopen'ing the real universal dylib under Rosetta 2.
    host_cpp = tmp / "rosetta_host.cpp"
    host_bin = tmp / "rosetta_host"
    host_cpp.write_text(
        '#include <atomic>\n'
        '#include <cstdio>\n'
        '#include <cstdlib>\n'
        '#include <cstring>\n'
        '#include <dlfcn.h>\n'
        '#include <fcntl.h>\n'
        '#include <mach/mach.h>\n'
        '#include <mach/mach_vm.h>\n'
        '#include <pthread.h>\n'
        '#include <sys/mman.h>\n'
        '#include <unistd.h>\n'
        '#include "MailboxProtocol.h"\n'
        '\n'
        'struct MockHadesApp {\n'
        '    virtual void Init() {}\n'
        '    virtual void Update(float dt) { ticks += (dt > 0.0f ? 1 : 0); }\n'
        '    virtual ~MockHadesApp() = default;\n'
        '    uint64_t ticks = 0;\n'
        '};\n'
        '\n'
        'static MGTMailboxSlot *g_slot = nullptr;\n'
        'static uint64_t g_hi = 0, g_lo = 0;\n'
        'typedef void (*UpdateFn)(MockHadesApp *, float);\n'
        'static UpdateFn g_orig_update = nullptr;\n'
        'static std::atomic<bool> g_stop{false};\n'
        '\n'
        'static void *bg_allocator(void *) {\n'
        '    while (!g_stop.load(std::memory_order_relaxed)) {\n'
        '        void *p = std::malloc(256);\n'
        '        std::memset(p, 0xA5, 256);\n'
        '        std::free(p);\n'
        '    }\n'
        '    return nullptr;\n'
        '}\n'
        '\n'
        'static void hooked_update(MockHadesApp *self, float dt) {\n'
        '    mgt_mailbox_tick(g_slot, mgt_mailbox_monotonic_ns());\n'
        '    MGTMailboxRequest req;\n'
        '    if (mgt_mailbox_claim(g_slot, g_hi, g_lo, &req) == MGT_MAILBOX_OK) {\n'
        '        char buf[128];\n'
        '        int len = std::snprintf(buf, sizeof(buf), "{\\"seq\\":%llu,\\"len\\":%zu}",\n'
        '                                (unsigned long long)req.sequence, req.length);\n'
        '        mgt_mailbox_complete(g_slot, g_hi, g_lo, req.sequence,\n'
        '                             MGT_MAILBOX_SUCCESS, 0, buf, (size_t)len, 1000);\n'
        '    }\n'
        '    g_orig_update(self, dt);\n'
        '}\n'
        '\n'
        'int main(int argc, char **argv) {\n'
        '    if (argc < 5) return 2;\n'
        '    void *lib = dlopen(argv[1], RTLD_NOW);\n'
        '    if (!lib) { std::fprintf(stderr, "dlopen: %s\\n", dlerror()); return 3; }\n'
        '    auto abi_fn = (uint32_t(*)())dlsym(lib, "MGTMailboxABI");\n'
        '    auto inst_fn = dlsym(lib, "MGTCommandMailboxInstall");\n'
        '    if (!abi_fn || abi_fn() != MGT_MAILBOX_ABI || !inst_fn) return 4;\n'
        '    g_hi = std::strtoull(argv[3], nullptr, 16);\n'
        '    g_lo = std::strtoull(argv[4], nullptr, 16);\n'
        '    int fd = open(argv[2], O_RDWR | O_NOFOLLOW | O_CLOEXEC);\n'
        '    if (fd < 0) return 5;\n'
        '    g_slot = (MGTMailboxSlot *)mmap(nullptr, sizeof(MGTMailboxSlot),\n'
        '                                     PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);\n'
        '    close(fd);\n'
        '    if (g_slot == MAP_FAILED) return 6;\n'
        '    MockHadesApp app;\n'
        '    uintptr_t **vptr = *(uintptr_t ***)&app;\n'
        '    g_orig_update = (UpdateFn)vptr[1];\n'
        '    mach_vm_address_t page = ((uintptr_t)&vptr[1]) & ~((mach_vm_address_t)vm_page_size - 1);\n'
        '    mach_vm_protect(mach_task_self(), page, vm_page_size, FALSE, VM_PROT_READ | VM_PROT_WRITE);\n'
        '    atomic_thread_fence(memory_order_seq_cst);\n'
        '    *((uintptr_t *)&vptr[1]) = (uintptr_t)hooked_update;\n'
        '    pthread_t th;\n'
        '    pthread_create(&th, nullptr, bg_allocator, nullptr);\n'
        '    std::puts("READY");\n'
        '    std::fflush(stdout);\n'
        '    MockHadesApp *volatile papp = &app;\n'
        '    while ((mgt_mailbox_flags(g_slot) & MGT_MAILBOX_CLOSED_FLAG) == 0) {\n'
        '        papp->Update(0.016f);\n'
        '        usleep(500);\n'
        '    }\n'
        '    g_stop.store(true, std::memory_order_relaxed);\n'
        '    pthread_join(th, nullptr);\n'
        '    munmap(g_slot, sizeof(MGTMailboxSlot));\n'
        '    return 0;\n'
        '}\n',
        encoding="utf-8",
    )
    subprocess.run([
        clangxx, "-std=c++17", "-arch", "x86_64", "-isysroot", sdk,
        "-mmacosx-version-min=14.0", "-Wall", "-Wextra", "-Werror",
        "-I", str(ROOT / "Backend/games/hades/native"),
        str(host_cpp), "-lpthread", "-o", str(host_bin),
    ], check=True)
    subprocess.run(["xcrun", "lipo", str(host_bin), "-verify_arch", "x86_64"], check=True)

    # Pre-create the mailbox with a placeholder pid, spawn Rosetta host, or set target_pid after fork:
    # Actually allocate shared file, spawn x86_64 child paused? Even simpler: let Mailbox init with os.getpid()
    # or check MGTMailboxValidate accepts any valid pid != 0! Wait: parent initializes mailbox with child pid,
    # so let's open via ctypes only AFTER knowing child's pid, or wait for host via FIFO/pipe before init?
    # Simpler: create empty file via tempfile, start host? No, host checks MGTMailboxSlot on mmap, or just
    # spawn via os.fork() where child waits on a pipe for "GO\n" and parent passes child.pid to HadesCommandMailbox!
    fifo = tmp / "start.fifo"
    os.mkfifo(fifo)
    args_file = tmp / "args.json"
    proc = subprocess.Popen(
        [
            "arch", "-x86_64", "/bin/sh", "-c",
            f"read _ < '{fifo}' && set -- $(cat '{args_file}') && exec '{host_bin}' \"$@\"",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        mb = HadesCommandMailbox(dylib_path, proc.pid, alive=lambda: proc.poll() is None)
        args_file.write_text(
            f"{dylib_path} {mb.path} {mb.generation_hi:x} {mb.generation_lo:x}",
            encoding="utf-8",
        )
        with open(fifo, "w", encoding="utf-8") as wake:
            wake.write("go\n")
        ready_line = proc.stdout.readline().strip()
        assert ready_line == "READY", f"Rosetta host failed: {ready_line!r} stderr={proc.stderr.read()}"
        mb.installed_in_target()

        for index in range(1, 201):
            reply = json.loads(mb.execute(f"return {index}", timeout_seconds=5.0, mutating=True))
            mb.acknowledge()
            assert reply["seq"] == index, reply
        snap = mb.diagnostics()
        assert snap["heartbeatCount"] > 0 and snap["completedCount"] == 200, snap
        mb.close()
        rc = proc.wait(timeout=5)
        assert rc == 0, f"Rosetta host exited with {rc}: {proc.stderr.read()}"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

print("hades_rosetta_mailbox_macos_ok")
