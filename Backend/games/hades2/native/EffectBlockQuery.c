/* Hades II 1.143476 / Steam 25481925, arm64 only. No engine mutations. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <limits.h>
#ifdef __APPLE__
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <pthread.h>
#endif

#define EXPORT __attribute__((visibility("default")))
#define QUERY_ABI 1
#define MAX_BLOCKS 256
#define MAX_BUCKETS 4096
#define MAX_NAME 256
#define INTERN_CAPACITY 0xC00000

typedef struct lua_State lua_State;
typedef int (*lua_CFunction)(lua_State *);
typedef int (*ReadMemory)(uintptr_t, void *, size_t, void *);
typedef void *(*FindUnit)(void *, int32_t);

typedef struct {
    uintptr_t world, strings, staticStrings, stringLength;
    FindUnit findUnit;
} Layout;

typedef struct {
    uintptr_t unit;
    size_t count;
    char names[MAX_BLOCKS][MAX_NAME];
} Snapshot;

static Layout layout;

static int readSelf(uintptr_t address, void *destination, size_t size, void *context) {
    (void)context;
    if (!address || address > UINTPTR_MAX - size) return 0;
#ifdef __APPLE__
    mach_vm_size_t copied = 0;
    return mach_vm_read_overwrite(mach_task_self(), address, size,
        (mach_vm_address_t)destination, &copied) == KERN_SUCCESS && copied == size;
#else
    (void)destination;
    return 0;
#endif
}

/* Return 1 for a validated Unit, 0 for absent, -1 for unreadable/invalid state. */
static int unitIdentity(const Layout *profile, ReadMemory read, void *context,
                        int32_t objectId, uintptr_t *unit) {
    uintptr_t world = 0;
    if (!read(profile->world, &world, sizeof(world), context)) return -1;
    if (!world) return 0;
    uintptr_t target = (uintptr_t)profile->findUnit((void *)world, objectId);
    if (!target) return 0;
    uint32_t type = 0;
    int32_t storedId = 0;
    if (target > UINTPTR_MAX - 0x800
        || !read(target + 0x8, &type, sizeof(type), context)
        || !read(target + 0x48, &storedId, sizeof(storedId), context)
        || (type & 0x111) != 0x111 || storedId != objectId) return -1;
    *unit = target;
    return 1;
}

/* Collect first; Lua table/string allocation can run native game finalizers. */
static int collect(const Layout *profile, ReadMemory read, void *context,
                   int32_t objectId, Snapshot *snapshot) {
    snapshot->count = 0;
    int found = unitIdentity(profile, read, context, objectId, &snapshot->unit);
    if (found != 1) return found;
    uintptr_t buckets = 0, strings = 0;
    uint32_t bucketCount = 0, stringLength = 0;
    uint64_t count = 0;
    uintptr_t unit = snapshot->unit;
    if (!read(unit + 0x770, &buckets, sizeof(buckets), context)
        || !read(unit + 0x778, &bucketCount, sizeof(bucketCount), context)
        || !read(unit + 0x780, &count, sizeof(count), context)
        || !buckets || !bucketCount || bucketCount > MAX_BUCKETS || count > MAX_BLOCKS
        || buckets > UINTPTR_MAX - bucketCount * sizeof(uintptr_t)) return -1;
    if (count && (!read(profile->strings, &strings, sizeof(strings), context)
        || !read(profile->stringLength, &stringLength, sizeof(stringLength), context)
        || strings != profile->staticStrings || stringLength > INTERN_CAPACITY)) return -1;
    uintptr_t visited[MAX_BLOCKS];
    for (uint32_t bucket = 0; bucket < bucketCount; ++bucket) {
        uintptr_t node = 0;
        if (!read(buckets + bucket * sizeof(uintptr_t), &node, sizeof(node), context)) return -1;
        /* The sentinel is at buckets[bucketCount]; it is never traversed. */
        while (node) {
            if (snapshot->count >= count || node > UINTPTR_MAX - 16) return -1;
            for (size_t index = 0; index < snapshot->count; ++index)
                if (visited[index] == node) return -1;
            uint32_t guid = 0;
            uintptr_t next = 0;
            if (!read(node, &guid, sizeof(guid), context)
                || !read(node + 8, &next, sizeof(next), context)
                || guid >= stringLength) return -1;
            size_t available = stringLength - guid;
            if (available > MAX_NAME) available = MAX_NAME;
            char *name = snapshot->names[snapshot->count];
            if (!read(strings + guid, name, available, context)
                || !memchr(name, 0, available)) return -1;
            visited[snapshot->count++] = node;
            node = next;
        }
    }
    return snapshot->count == count ? 1 : -1;
}

/* Exact Lua 5.2 ABI and target-image RVAs. UUID validation owns these offsets. */
#define LUA_APIS(X) \
    X(int, gettop, (lua_State *), 0x14248, "080840f9091040f9290140f9080109cb") \
    X(void, settop, (lua_State *, int), 0x14264, "c101f837081040f9080140f90851218b") \
    X(int, checkstack, (lua_State *, int), 0x140dc, "ffc300d1f44f01a9fd7b02a9fd830091") \
    X(int, type, (lua_State *, int), 0x14538, "fd7bbfa9fd03009171ffff97481c00d0") \
    X(double, tonumberx, (lua_State *, int, int *), 0x14770, "ffc300d1f44f01a9fd7b02a9fd830091") \
    X(void, pushinteger, (lua_State *, ptrdiff_t), 0x14b04, "080840f92000629e000100fd69008052") \
    X(void, pushnil, (lua_State *), 0x14ad0, "080840f91f0900b908410091080800f9") \
    X(const char *, pushlstring, (lua_State *, const char *, size_t), 0x14b58, "f657bda9f44f01a9fd7b02a9fd830091") \
    X(void, pushcclosure, (lua_State *, lua_CFunction, int), 0x14cfc, "f657bda9f44f01a9fd7b02a9fd830091") \
    X(void, pushboolean, (lua_State *, int), 0x14dc4, "080840f93f000071e9079f1a090100b9") \
    X(void, pushlightuserdata, (lua_State *, void *), 0x14dec, "080840f9010100f949008052090900b9") \
    X(void, createtable, (lua_State *, int, int), 0x14fe0, "f657bda9f44f01a9fd7b02a9fd830091") \
    X(void, setfield, (lua_State *, int, const char *), 0x15214, "f657bda9f44f01a9fd7b02a9fd830091") \
    X(void, rawgeti, (lua_State *, int, int), 0x14f90, "f44fbea9fd7b01a9fd430091f30302aa") \
    X(void, rawset, (lua_State *, int), 0x15290, "f657bda9f44f01a9fd7b02a9fd830091") \
    X(int, pcallk, (lua_State *, int, int, int, int, lua_CFunction), 0x155b4, "ff4301d1f85f01a9f65702a9f44f03a9")

#define DECLARE_API(result, name, arguments, rva, prefix) result (*name) arguments;
static struct { LUA_APIS(DECLARE_API) } api;
#undef DECLARE_API

static int queryError(lua_State *state, const char *message) {
    api.pushnil(state);
    api.pushlstring(state, message, strlen(message));
    return 2;
}

static int objectId(lua_State *state, int32_t *result) {
    int numeric = 0;
    double number = api.tonumberx(state, 1, &numeric);
    if (api.type(state, 1) != 3 || !numeric || !isfinite(number)
        || number < 1 || number > INT32_MAX || floor(number) != number) return 0;
    *result = (int32_t)number;
    return 1;
}

static int callableThread(void) {
#ifdef __APPLE__
    return pthread_main_np();
#else
    return 0;
#endif
}

static int queryIdentity(lua_State *state) {
    int32_t id = 0;
    uintptr_t unit = 0;
    if (!callableThread() || !objectId(state, &id)) return queryError(state, "Native Unit query requires MainThread and an integer ObjectId");
    int result = unitIdentity(&layout, readSelf, NULL, id, &unit);
    if (result < 0) return queryError(state, "Native Unit identity is unreadable or invalid");
    if (!result) { api.pushnil(state); return 1; }
    api.pushlightuserdata(state, (void *)unit);
    return 1;
}

static int querySnapshot(lua_State *state) {
    int32_t id = 0;
    Snapshot snapshot;
    if (!callableThread() || !objectId(state, &id)) return queryError(state, "Native effect-block query requires MainThread and an integer ObjectId");
    int result = collect(&layout, readSelf, NULL, id, &snapshot);
    if (result != 1) return queryError(state, result ? "Native effect-block set is unreadable or invalid" : "Native Hero unit is unavailable");
    api.createtable(state, 0, 3);
    api.pushinteger(state, id); api.setfield(state, -2, "objectId");
    api.pushlightuserdata(state, (void *)snapshot.unit); api.setfield(state, -2, "unitToken");
    api.createtable(state, 0, (int)snapshot.count);
    for (size_t index = 0; index < snapshot.count; ++index) {
        api.pushboolean(state, 1); api.setfield(state, -2, snapshot.names[index]);
    }
    api.setfield(state, -2, "blocked");
    return 1;
}

static int registerQueries(lua_State *state) {
    api.rawgeti(state, -1001000, 2); /* Lua 5.2 registry -> globals. */
    api.pushlstring(state, "__MGTHadesNativeV1", sizeof("__MGTHadesNativeV1") - 1);
    api.createtable(state, 0, 3);
    api.pushinteger(state, QUERY_ABI); api.setfield(state, -2, "abi");
    api.pushcclosure(state, queryIdentity, 0); api.setfield(state, -2, "unitIdentity");
    api.pushcclosure(state, querySnapshot, 0); api.setfield(state, -2, "snapshotEffectBlocks");
    api.rawset(state, -3); /* Private publication must not invoke __newindex. */
    api.settop(state, -2);
    return 0;
}

#ifdef __APPLE__
static int prefixMatches(uintptr_t address, const char *hex) {
    uint8_t bytes[16];
    if (!readSelf(address, bytes, sizeof(bytes), NULL)) return 0;
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

static int configure(void) {
    const struct mach_header_64 *header = (const struct mach_header_64 *)_dyld_get_image_header(0);
    if (!header || header->magic != MH_MAGIC_64 || header->filetype != MH_EXECUTE
        || header->cputype != CPU_TYPE_ARM64 || header->sizeofcmds > 65536) return 0;
    static const uint8_t expected[16] = { 0x35,0xcd,0x2e,0x50,0x2d,0x78,0x3a,0x63,0x83,0x5b,0x3e,0xb1,0x22,0x4c,0x6d,0x65 };
    const uint8_t *cursor = (const uint8_t *)(header + 1);
    const uint8_t *end = cursor + header->sizeofcmds;
    int uuidMatches = 0;
    for (uint32_t index = 0; index < header->ncmds; ++index) {
        if ((size_t)(end - cursor) < sizeof(struct load_command)) return 0;
        const struct load_command *command = (const struct load_command *)cursor;
        if (command->cmdsize < sizeof(*command) || command->cmdsize > (size_t)(end - cursor)) return 0;
        if (command->cmd == LC_UUID) {
            if (command->cmdsize != sizeof(struct uuid_command)) return 0;
            uuidMatches = memcmp(((const struct uuid_command *)command)->uuid, expected, 16) == 0;
        }
        cursor += command->cmdsize;
    }
    if (!uuidMatches) return 0;
    uintptr_t base = (uintptr_t)header;
    if (!prefixMatches(base + 0x258b70, "287c409309d041f9287d089b088548ca")) return 0;
#define RESOLVE_API(result, name, arguments, rva, prefix) \
    if (!prefixMatches(base + rva, prefix)) return 0; \
    api.name = (result (*) arguments)(base + rva);
    LUA_APIS(RESOLVE_API)
#undef RESOLVE_API
    layout = (Layout){ base + 0x511eaa8, base + 0x64b8630, base + 0x541f2a0,
        base + 0x601f2a0, (FindUnit)(base + 0x258b70) };
    return 1;
}
#else
static int configure(void) { return 0; }
#endif

EXPORT uint32_t MGTNativeEffectQueryABI(void) { return QUERY_ABI; }

/* The image remains loaded for process lifetime. No scratch/JIT code is retained.
 * On success preserve the Lua stack; on protected Lua error leave its diagnostic
 * for the transport to copy and pop. Negative results never touched Lua. */
static int installQueries(lua_State *state) {
    if (!api.checkstack(state, 1)) return -2;
    int top = api.gettop(state);
    api.pushcclosure(state, registerQueries, 0); /* zero upvalues: no allocation */
    int result = api.pcallk(state, 0, 0, 0, 0, NULL);
    if (!result) api.settop(state, top);
    return result;
}

EXPORT int MGTNativeEffectQueryInstall(lua_State *state) {
    if (!callableThread() || !configure()) return -1;
    return installQueries(state);
}
