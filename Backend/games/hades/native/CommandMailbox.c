/* Hades I command transport. Protocol entry points are compiled for both
 * arm64 (producer) and x86_64 (target consumer under Rosetta 2), so every
 * shared-memory transition uses the same C11 ABI. The target hook replaces
 * sgg::HadesApp::Update(float) via its writable __DATA vtable slot with zero
 * __TEXT patching. */
#if !defined(__APPLE__) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#include "MailboxProtocol.h"
#include "SupportedBuildIdentity.h"

#define EXPORT __attribute__((visibility("default")))

EXPORT uint32_t MGTMailboxABI(void) { return MGT_MAILBOX_ABI; }
EXPORT size_t MGTMailboxSize(void) { return sizeof(MGTMailboxSlot); }
EXPORT int MGTMailboxInit(void *memory, size_t size, uint64_t hi, uint64_t lo,
                          uint32_t producer, uint32_t target) {
    if (size != sizeof(MGTMailboxSlot)) return MGT_MAILBOX_INVALID;
    return mgt_mailbox_init(memory, hi, lo, producer, target);
}
EXPORT int MGTMailboxSubmit(void *memory, uint64_t hi, uint64_t lo, uint64_t sequence,
                            const void *source, size_t length) {
    return mgt_mailbox_submit(memory, hi, lo, sequence, source, length);
}
EXPORT int MGTMailboxRead(void *memory, uint64_t hi, uint64_t lo, uint64_t sequence,
                          MGTMailboxReceipt *receipt, void *output, size_t capacity) {
    return mgt_mailbox_read(memory, hi, lo, sequence, receipt, output, capacity);
}
EXPORT int MGTMailboxAck(void *memory, uint64_t hi, uint64_t lo, uint64_t sequence) {
    return mgt_mailbox_ack(memory, hi, lo, sequence);
}
EXPORT int MGTMailboxCancel(void *memory, uint64_t hi, uint64_t lo, uint64_t sequence) {
    return mgt_mailbox_cancel(memory, hi, lo, sequence);
}
EXPORT int MGTMailboxClose(void *memory, uint64_t hi, uint64_t lo) {
    return mgt_mailbox_close(memory, hi, lo);
}
EXPORT int MGTMailboxPoison(void *memory, uint64_t hi, uint64_t lo) {
    return mgt_mailbox_poison(memory, hi, lo);
}
EXPORT uint32_t MGTMailboxGetState(void *memory) {
    return memory == NULL ? UINT32_MAX : mgt_mailbox_state(memory);
}

/* Diagnostic snapshots never claim or acknowledge a request. Counters can
 * advance independently while sampled; receipt identity remains authoritative. */
EXPORT int MGTMailboxDiagnostics(void *memory, uint64_t hi, uint64_t lo,
                                 uint64_t *output, size_t count) {
    MGTMailboxSlot *slot = memory;
    int result = mgt_mailbox_validate(slot, hi, lo);
    if (result != MGT_MAILBOX_OK) return result;
    if (output == NULL || count < 6) return MGT_MAILBOX_CAPACITY;
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    output[0] = control & MGT_MAILBOX_STATE_MASK;
    output[1] = control & MGT_MAILBOX_LEASE_FLAGS;
    output[2] = atomic_load_explicit(&slot->heartbeat_count, memory_order_acquire);
    output[3] = atomic_load_explicit(&slot->heartbeat_ns, memory_order_relaxed);
    output[4] = atomic_load_explicit(&slot->claimed_count, memory_order_relaxed);
    output[5] = atomic_load_explicit(&slot->completed_count, memory_order_relaxed);
    return MGT_MAILBOX_OK;
}

#if defined(MGT_MAILBOX_RUNTIME_TEST) || (defined(__APPLE__) && defined(__x86_64__) && !defined(MGT_MAILBOX_PORTABLE_TEST))
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#if !defined(MGT_MAILBOX_RUNTIME_TEST)
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <pthread.h>
#endif
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

typedef struct lua_State lua_State;
typedef int (*LuaCFunction)(lua_State *);

/* Exact Lua 5.2 API and supported x86_64 Game.macOS image. */
#define LUA_APIS(X) \
    X(int, gettop, (lua_State *), 0x27ad, "554889e5488b4710488b4f20482b0148") \
    X(void, settop, (lua_State *, int), 0x27c6, "554889e585f67836488b4710488b4f20") \
    X(int, checkstack, (lua_State *, int), 0x2634, "554889e54157415653508975e4488b47") \
    X(int, type, (lua_State *, int), 0x2a08, "554889e5e84afeffff483b05085a5200") \
    X(const char *, tolstring, (lua_State *, int, size_t *), 0x2cdd, "554889e54157415653504989d64189f7") \
    X(const char *, pushlstring, (lua_State *, const char *, size_t), 0x2efd, "554889e54157415653504989d64989f7") \
    X(void, pushcclosure, (lua_State *, LuaCFunction, int), 0x30d0, "554889e54157415653504989f74889fb") \
    X(void, pushlightuserdata, (lua_State *, void *), 0x3190, "554889e5488b4710488930c740080200") \
    X(void, rawget, (lua_State *, int), 0x32ca, "554889e553504889fbe883f5ffff488b") \
    X(void, rawset, (lua_State *, int), 0x356d, "554889e54157415653504989ffe8dcf2") \
    X(int, loadbufferx, (lua_State *, const char *, size_t, const char *, const char *), 0x191e1, "554889e54883ec10488d45f048893048") \
    X(int, pcallk, (lua_State *, int, int, int, int, LuaCFunction), 0x37e8, "554889e54157415641554154534883ec")

#define DECLARE_API(result, name, arguments, rva, prefix) result (*name) arguments;
typedef struct {
    LUA_APIS(DECLARE_API)
} LuaAPI;
#undef DECLARE_API

enum {
    INSTALL_FAILURE = MGT_MAILBOX_INSTALL_FAILURE,
    INSTALL_RESTART_REQUIRED = MGT_MAILBOX_INSTALL_RESTART_REQUIRED,
    GENERATION_CHANGED = -1000,
    STACK_UNAVAILABLE = -1001,
    LUA_REGISTRY = -1001000,
    LUA_STRING = 4
};

#define HADES_APP_UPDATE_RVA ((uintptr_t)UINT64_C(0x0c4b80))
#define HADES_APP_VTABLE_RVA ((uintptr_t)UINT64_C(0x52e2c8))
#define HADES_APP_UPDATE_VSLOT_RVA ((uintptr_t)UINT64_C(0x52e2f8))
#define LUA_INTERFACE_RVA ((uintptr_t)UINT64_C(0x5430a8))
#define HADES_APP_UPDATE_PREFIX "554889e54157415641554154534883ec"

typedef struct {
    MGTMailboxSlot *slot;
    lua_State *state;
    uint64_t hi, lo;
} MailboxLease;

static LuaAPI lua;
static uintptr_t image_base;
static MailboxLease active_lease;
static MailboxLease *installing_lease;
#if !defined(MGT_MAILBOX_RUNTIME_TEST)
typedef void (*HadesAppUpdateFn)(void *self, float delta_time);
static HadesAppUpdateFn original_hades_app_update;
static int hook_installed;
#endif
static int in_pump;
static int installing;
static int process_tainted;
static char registry_key;

static void mgtCommandMailboxPump(void);

#if !defined(MGT_MAILBOX_RUNTIME_TEST)
static void mgtHadesAppUpdateHook(void *self, float delta_time) {
    mgtCommandMailboxPump();
    if (original_hades_app_update != NULL) {
        original_hades_app_update(self, delta_time);
    }
}
#endif

static int failure(char *output, size_t capacity, int status, const char *message) {
    if (output != NULL && capacity != 0) {
        snprintf(output, capacity, "%s", message);
        output[capacity - 1] = 0;
    }
    return status;
}

#if !defined(MGT_MAILBOX_RUNTIME_TEST)
static int readSelf(uintptr_t address, void *destination, size_t size) {
    if (address == 0 || address > UINTPTR_MAX - size) return 0;
    mach_vm_size_t copied = 0;
    return mach_vm_read_overwrite(mach_task_self(), address, size,
        (mach_vm_address_t)destination, &copied) == KERN_SUCCESS && copied == size;
}

static int prefixMatches(uintptr_t address, const char *hex) {
    uint8_t bytes[16];
    if (!readSelf(address, bytes, sizeof(bytes))) return 0;
    for (size_t index = 0; index < sizeof(bytes); ++index) {
        unsigned value = 0;
        for (size_t digit = 0; digit < 2; ++digit) {
            char c = hex[2 * index + digit];
            value = value * 16 + (unsigned)(c <= '9' ? c - '0' : c - 'a' + 10);
        }
        if (bytes[index] != value) return 0;
    }
    return 1;
}

static int verifyImage(uintptr_t base, char *output, size_t capacity) {
    uintptr_t max_rva = LUA_INTERFACE_RVA > HADES_APP_UPDATE_VSLOT_RVA
        ? LUA_INTERFACE_RVA : HADES_APP_UPDATE_VSLOT_RVA;
    uint32_t header[8];
    if (base == 0 || base > UINTPTR_MAX - max_rva - sizeof(void *)
        || !readSelf(base, header, sizeof(header)) || header[0] != UINT32_C(0xfeedfacf)
        || header[1] != UINT32_C(0x01000007) || header[3] != 2
        || header[5] > 65536 || header[4] > header[5] / 8)
        return failure(output, capacity, INSTALL_FAILURE, "Unsupported Hades executable header");
    static const uint8_t expected_uuid[16] = { MGT_SUPPORTED_GAME_UUID_BYTES };
    uintptr_t cursor = base + sizeof(header), end = cursor + header[5];
    int uuid_matches = 0;
    for (uint32_t index = 0; index < header[4]; ++index) {
        uint32_t command[2];
        if (cursor > end || end - cursor < sizeof(command)
            || !readSelf(cursor, command, sizeof(command))
            || command[1] < sizeof(command) || command[1] > end - cursor)
            return failure(output, capacity, INSTALL_FAILURE, "Invalid Hades image load commands");
        if (command[0] == 0x1b) {
            uint8_t uuid[16];
            if (command[1] != sizeof(command) + sizeof(uuid)
                || !readSelf(cursor + sizeof(command), uuid, sizeof(uuid)))
                return failure(output, capacity, INSTALL_FAILURE, "Invalid Hades image UUID command");
            uuid_matches = memcmp(uuid, expected_uuid, sizeof(uuid)) == 0;
        }
        cursor += command[1];
    }
    if (!uuid_matches)
        return failure(output, capacity, INSTALL_FAILURE, "Mailbox requires " MGT_SUPPORTED_GAME_DESCRIPTION);
    LuaAPI candidate;
#define RESOLVE_API(result, name, arguments, rva, prefix) \
    if (!prefixMatches(base + rva, prefix)) \
        return failure(output, capacity, INSTALL_FAILURE, "Hades Lua binding mismatch: " #name); \
    candidate.name = (result (*) arguments)(base + rva);
    LUA_APIS(RESOLVE_API)
#undef RESOLVE_API
    if (!prefixMatches(base + HADES_APP_UPDATE_RVA, HADES_APP_UPDATE_PREFIX))
        return failure(output, capacity, INSTALL_FAILURE, "HadesApp::Update entry prologue mismatch");
    uintptr_t current_vslot = 0;
    if (!readSelf(base + HADES_APP_UPDATE_VSLOT_RVA, &current_vslot, sizeof(current_vslot)))
        return failure(output, capacity, INSTALL_FAILURE, "Cannot read HadesApp::Update vtable slot");
    if (hook_installed) {
        if (base != image_base || current_vslot != (uintptr_t)mgtHadesAppUpdateHook)
            return failure(output, capacity, INSTALL_RESTART_REQUIRED, "Existing mailbox hook has changed");
    } else if (current_vslot != base + HADES_APP_UPDATE_RVA) {
        return failure(output, capacity, INSTALL_RESTART_REQUIRED,
                       "HadesApp::Update vtable slot is already modified or incompatible with this mailbox");
    }
    lua = candidate;
    return 0;
}

/* Installation runs only at a verified main-thread debugger boundary with all
 * other threads stopped. Updates only the writable __DATA vtable slot. */
static int installHook(uintptr_t base, char *output, size_t capacity) {
    if (hook_installed) return 0;
    uintptr_t vslot = base + HADES_APP_UPDATE_VSLOT_RVA;
    if ((vslot % sizeof(uintptr_t)) != 0)
        return failure(output, capacity, INSTALL_FAILURE, "Unaligned HadesApp::Update vtable slot");
    mach_vm_address_t region = vslot;
    mach_vm_size_t region_size = 0;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t object = MACH_PORT_NULL;
    kern_return_t result = mach_vm_region(mach_task_self(), &region, &region_size,
        VM_REGION_BASIC_INFO_64, (vm_region_info_t)&info, &count, &object);
    if (object != MACH_PORT_NULL) mach_port_deallocate(mach_task_self(), object);
    if (result != KERN_SUCCESS || region > vslot || region_size < sizeof(uintptr_t)
        || vslot - region > region_size - sizeof(uintptr_t)
        || (info.protection & VM_PROT_EXECUTE))
        return failure(output, capacity, INSTALL_FAILURE, "Cannot identify writable HadesApp vtable memory");
    int changed_protection = 0;
    mach_vm_address_t page = vslot & ~((mach_vm_address_t)vm_page_size - 1);
    if (vslot + sizeof(uintptr_t) > page + vm_page_size)
        return failure(output, capacity, INSTALL_FAILURE, "Unsupported HadesApp vtable page boundary");
    if (!(info.protection & VM_PROT_WRITE)) {
        result = mach_vm_protect(mach_task_self(), page, vm_page_size, FALSE,
                                 info.protection | VM_PROT_WRITE);
        if (result != KERN_SUCCESS)
            return failure(output, capacity, INSTALL_FAILURE, "Cannot prepare writable HadesApp vtable page");
        changed_protection = 1;
    }
    original_hades_app_update = (HadesAppUpdateFn)(base + HADES_APP_UPDATE_RVA);
    atomic_store_explicit((_Atomic uintptr_t *)vslot, (uintptr_t)mgtHadesAppUpdateHook, memory_order_release);
    if (changed_protection) {
        result = mach_vm_protect(mach_task_self(), page, vm_page_size, FALSE, info.protection);
        if (result != KERN_SUCCESS) {
            process_tainted = 1;
            return failure(output, capacity, INSTALL_RESTART_REQUIRED,
                           "Cannot restore HadesApp vtable page protection after installing mailbox hook");
        }
    }
    image_base = base;
    hook_installed = 1;
    return 0;
}
#endif

static int producerAlive(uint32_t pid) {
    if (kill((pid_t)pid, 0) == 0) return 1;
    return errno != ESRCH; /* Permission/temporary failures do not prove death. */
}

/* A successful, unacknowledged action remains evidence in the target even if
 * its producer dies. Replacing its mapping must never erase that uncertainty. */
static int canRetireLease(char *output, size_t capacity) {
    MGTMailboxSlot *slot = active_lease.slot;
    if (process_tainted)
        return failure(output, capacity, INSTALL_RESTART_REQUIRED, "The game's previous command outcome is unknown");
    if (slot == NULL) return 0;
    if (mgt_mailbox_validate(slot, active_lease.hi, active_lease.lo) != MGT_MAILBOX_OK
        || (mgt_mailbox_flags(slot) & MGT_MAILBOX_POISONED_FLAG)) {
        process_tainted = 1;
        return failure(output, capacity, INSTALL_RESTART_REQUIRED, "The previous mailbox lease is invalid or poisoned");
    }
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    /* A live, open producer still owns both its publication and receipt. Do
     * not turn a competing attachment into a failure of that active lease. */
    if (!(control & MGT_MAILBOX_CLOSED_FLAG) && producerAlive(slot->producer_pid))
        return failure(output, capacity, INSTALL_FAILURE, "Another live producer owns this mailbox");
    uint32_t state = control & MGT_MAILBOX_STATE_MASK;
    if (state == MGT_MAILBOX_COMPLETE
        && (slot->outcome == MGT_MAILBOX_CANCELLED
            || (slot->outcome == MGT_MAILBOX_ERROR
                && (slot->status == GENERATION_CHANGED || slot->status == STACK_UNAVAILABLE)))) {
        /* These receipts prove the source was never evaluated. Closed/dead
         * ownership makes their non-atomic fields stable, even without ACK. */
        mgt_mailbox_close(slot, active_lease.hi, active_lease.lo);
        return 0;
    }
    if (state != MGT_MAILBOX_IDLE) {
        process_tainted = 1;
        mgt_mailbox_poison(slot, active_lease.hi, active_lease.lo);
        return failure(output, capacity, INSTALL_RESTART_REQUIRED,
                       "The previous mailbox has an unacknowledged or unfinished command");
    }
    mgt_mailbox_close(slot, active_lease.hi, active_lease.lo);
    return 0;
}

static int writeRegistryToken(lua_State *state) {
    uint64_t token[2] = { installing_lease->hi, installing_lease->lo };
    lua.pushlightuserdata(state, &registry_key);
    lua.pushlstring(state, (const char *)token, sizeof(token));
    lua.rawset(state, LUA_REGISTRY);
    return 0;
}

static int bindGeneration(MailboxLease *lease) {
    lua_State *state = lease->state;
    installing_lease = lease;
    int top = lua.gettop(state);
    int result;
    if (!lua.checkstack(state, 8)) result = STACK_UNAVAILABLE;
    else {
        lua.pushcclosure(state, writeRegistryToken, 0);
        result = lua.pcallk(state, 0, 0, 0, 0, NULL);
    }
    lua.settop(state, top);
    installing_lease = NULL;
    return result;
}

static int generationMatches(const MailboxLease *lease) {
    lua_State *current = *(lua_State *volatile *)(image_base + LUA_INTERFACE_RVA);
    if (current != lease->state || current == NULL) return 0;
    int top = lua.gettop(current);
    lua.pushlightuserdata(current, &registry_key);
    lua.rawget(current, LUA_REGISTRY);
    const char *token = NULL;
    size_t size = 0;
    if (lua.type(current, -1) == LUA_STRING) token = lua.tolstring(current, -1, &size);
    const uint64_t expected[2] = { lease->hi, lease->lo };
    int matches = token != NULL && size == sizeof(expected) && memcmp(token, expected, sizeof(expected)) == 0;
    lua.settop(current, top);
    return matches;
}

static void finishRequest(MailboxLease *lease, const MGTMailboxRequest *request,
                          uint32_t outcome, int status, const char *result,
                          size_t length, uint64_t started) {
    if (outcome == MGT_MAILBOX_UNKNOWN) process_tainted = 1;
    int completed = mgt_mailbox_complete(lease->slot, lease->hi, lease->lo,
        request->sequence, outcome, status, result, length, mgt_mailbox_monotonic_ns() - started);
    if (completed != MGT_MAILBOX_OK || (mgt_mailbox_flags(lease->slot) & MGT_MAILBOX_POISONED_FLAG)) {
        process_tainted = 1;
        mgt_mailbox_poison(lease->slot, lease->hi, lease->lo);
    }
}

__attribute__((used, noinline)) static void mgtCommandMailboxPump(void) {
    /* A callback from any other engine thread may keep running its original
     * App update, but it must never read/write this main-thread Lua owner. */
    if (!pthread_main_np()) return;
    MailboxLease *lease = &active_lease;
    MGTMailboxSlot *slot = lease->slot;
    if (slot == NULL || in_pump || installing) return;
    uint32_t flags = mgt_mailbox_flags(slot);
    if (flags & MGT_MAILBOX_POISONED_FLAG) process_tainted = 1;
    if (flags != 0 || process_tainted) return;
    mgt_mailbox_tick(slot, mgt_mailbox_monotonic_ns());
    /* Empty frames perform no Lua access, allocation, I/O or process query. */
    if (mgt_mailbox_state(slot) != MGT_MAILBOX_POSTED) return;
    if (!producerAlive(slot->producer_pid)) {
        mgt_mailbox_close(slot, lease->hi, lease->lo);
        return;
    }
    MGTMailboxRequest request;
    int claimed = mgt_mailbox_claim(slot, lease->hi, lease->lo, &request);
    if (claimed != MGT_MAILBOX_OK) {
        if (claimed == MGT_MAILBOX_INVALID || claimed == MGT_MAILBOX_STALE) {
            process_tainted = 1;
            mgt_mailbox_poison(slot, lease->hi, lease->lo);
        }
        return;
    }
    /* The successful claim records this boundary. Reuse it rather than
     * sampling a later start that would leave native work unattributed. */
    uint64_t started = slot->submitted_ns + slot->queue_ns;
    in_pump = 1;
    lua_State *current = *(lua_State *volatile *)(image_base + LUA_INTERFACE_RVA);
    if (current != lease->state || current == NULL) {
        const char *message = "Lua generation changed before command execution";
        finishRequest(lease, &request, MGT_MAILBOX_ERROR, GENERATION_CHANGED,
                      message, strlen(message), started);
        mgt_mailbox_close(slot, lease->hi, lease->lo);
        in_pump = 0;
        return;
    }
    if (!lua.checkstack(current, 8)) {
        const char *message = "Lua stack capacity is unavailable before command execution";
        finishRequest(lease, &request, MGT_MAILBOX_ERROR, STACK_UNAVAILABLE,
                      message, strlen(message), started);
        in_pump = 0;
        return;
    }
    if (!generationMatches(lease)) {
        const char *message = "Lua registry generation changed before command execution";
        finishRequest(lease, &request, MGT_MAILBOX_ERROR, GENERATION_CHANGED,
                      message, strlen(message), started);
        mgt_mailbox_close(slot, lease->hi, lease->lo);
        in_pump = 0;
        return;
    }
    int top = lua.gettop(current);
    int status = lua.loadbufferx(current, (const char *)request.source, request.length,
                                 "MacGamingTrainer.Hades", NULL);
    if (status == 0) status = lua.pcallk(current, 0, 1, 0, 0, NULL);
    uint32_t outcome = status == 0 ? MGT_MAILBOX_SUCCESS : MGT_MAILBOX_ERROR;
    const char *result = "";
    size_t length = 0;
    if (status >= 0) {
        /* Type-check before tolstring: coercing a number can allocate outside
         * pcall and longjmp through this native caller. A receipt is a string. */
        if (lua.type(current, -1) != LUA_STRING) {
            result = "Lua did not return a string receipt";
            length = strlen(result);
            outcome = MGT_MAILBOX_UNKNOWN;
        } else {
            result = lua.tolstring(current, -1, &length);
            if (result == NULL || length > MGT_MAILBOX_RESULT_CAPACITY) {
                result = "Lua receipt exceeds mailbox capacity or is unavailable";
                length = strlen(result);
                outcome = MGT_MAILBOX_UNKNOWN;
            }
        }
    }
    /* Copy before popping the Lua value; its bytes belong to the Lua GC. */
    finishRequest(lease, &request, outcome, status, result, length, started);
    lua.settop(current, top);
    in_pump = 0;
}

#if !defined(MGT_MAILBOX_RUNTIME_TEST)
EXPORT int MGTCommandMailboxInstall(void *state_pointer, uintptr_t base, const char *path,
                                    uint64_t hi, uint64_t lo, volatile unsigned char *phase,
                                    char *output, size_t capacity) {
    if (output != NULL && capacity != 0) output[0] = 0;
    if (!pthread_main_np() || in_pump || installing)
        return failure(output, capacity, INSTALL_FAILURE, "Mailbox installation requires an idle game main thread");
    int result = canRetireLease(output, capacity);
    if (result != 0) return result;
    result = verifyImage(base, output, capacity);
    if (result != 0) return result;
    lua_State *current = NULL;
    if (state_pointer == NULL || !readSelf(base + LUA_INTERFACE_RVA, &current, sizeof(current))
        || current != state_pointer)
        return failure(output, capacity, INSTALL_FAILURE, "LuaInterface changed before mailbox installation");
    if (path == NULL || path[0] != '/' || strnlen(path, PATH_MAX) == PATH_MAX)
        return failure(output, capacity, INSTALL_FAILURE, "Invalid mailbox mapping path");
    int descriptor = open(path, O_RDWR | O_NOFOLLOW | O_CLOEXEC);
    if (descriptor < 0) return failure(output, capacity, INSTALL_FAILURE, "Cannot open mailbox mapping");
    struct stat metadata;
    int valid_file = fstat(descriptor, &metadata) == 0 && S_ISREG(metadata.st_mode)
        && metadata.st_uid == getuid() && (metadata.st_mode & 0777) == 0600
        && metadata.st_size == (off_t)sizeof(MGTMailboxSlot);
    if (!valid_file) {
        close(descriptor);
        return failure(output, capacity, INSTALL_FAILURE, "Invalid mailbox mapping ownership, mode or size");
    }
    MGTMailboxSlot *slot = mmap(NULL, sizeof(*slot), PROT_READ | PROT_WRITE, MAP_SHARED, descriptor, 0);
    close(descriptor);
    if (slot == MAP_FAILED) return failure(output, capacity, INSTALL_FAILURE, "Cannot map command storage");
    if (mgt_mailbox_validate(slot, hi, lo) != MGT_MAILBOX_OK || slot->target_pid != (uint32_t)getpid()
        || slot->producer_pid == (uint32_t)getpid() || !producerAlive(slot->producer_pid)
        || mgt_mailbox_state(slot) != MGT_MAILBOX_IDLE || mgt_mailbox_flags(slot) != 0
        || atomic_load_explicit(&slot->highest_sequence, memory_order_acquire) != 0) {
        munmap(slot, sizeof(*slot));
        return failure(output, capacity, INSTALL_FAILURE, "Mailbox identity is stale or already used");
    }
    MailboxLease candidate = { slot, current, hi, lo };
    installing = 1;
    if (phase != NULL) *phase = 1;
    result = bindGeneration(&candidate);
    if (phase != NULL) *phase = 2;
    if (result == 0) {
        if (mgt_mailbox_monotonic_ns() == 0)
            result = failure(output, capacity, INSTALL_FAILURE, "Cannot read mailbox monotonic clock");
        else result = installHook(base, output, capacity);
    } else result = failure(output, capacity, INSTALL_FAILURE, "Cannot bind mailbox Lua registry generation");
    if (result != 0) {
        mgt_mailbox_close(slot, hi, lo);
        munmap(slot, sizeof(*slot));
    } else {
        MGTMailboxSlot *retired = active_lease.slot;
        active_lease = candidate;
        if (retired != NULL) munmap(retired, sizeof(*retired));
    }
    installing = 0;
    return result;
}
#endif
#endif
