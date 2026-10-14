/* Exercise the actual private C implementation; no game process is involved. */
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#endif
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
#include "EffectBlockQuery.c"

static unsigned char fixtureUnit[0x800];
static uintptr_t fixtureWorld = 0x1234, fixtureBuckets[3];
static char fixtureNames[256] = "StasisStun\0Inked";
static uintptr_t fixtureStrings = (uintptr_t)fixtureNames;
static uint32_t fixtureStringLength = 17;
static struct Node { uint32_t guid, padding; uintptr_t next; } nodes[2];
static size_t allocations;
static int failGrowth;

static const uintptr_t imageBase = 0x100000000;
static unsigned char imageHeader[128];
static int brokenPrefix = -1, unreadablePrefix = -1;
static uintptr_t unreadableAddress;
#define PROFILE_PREFIX(result, name, arguments, rva, prefix) { rva, prefix },
static const struct { uintptr_t rva; const char *hex; } imagePrefixes[] = {
    { 0x258b70, "287c409309d041f9287d089b088548ca" },
    LUA_APIS(PROFILE_PREFIX)
};
#undef PROFILE_PREFIX

static int readImage(uintptr_t address, void *destination, size_t size, void *context) {
    (void)context;
    if (address == unreadableAddress) return 0;
    if (address >= imageBase && address - imageBase <= sizeof(imageHeader)
        && size <= sizeof(imageHeader) - (address - imageBase)) {
        memcpy(destination, imageHeader + (address - imageBase), size);
        return 1;
    }
    for (size_t index = 0; index < sizeof(imagePrefixes)/sizeof(imagePrefixes[0]); ++index) {
        if (address != imageBase + imagePrefixes[index].rva || size != 16) continue;
        if ((int)index == unreadablePrefix) return 0;
        unsigned char bytes[16];
        for (size_t offset = 0; offset < sizeof(bytes); ++offset) {
            unsigned value;
            assert(sscanf(imagePrefixes[index].hex + 2 * offset, "%2x", &value) == 1);
            bytes[offset] = (unsigned char)value;
        }
        if ((int)index == brokenPrefix) bytes[0] ^= 1;
        memcpy(destination, bytes, sizeof(bytes));
        return 1;
    }
    return 0;
}

static void setupImage(void) {
    const uint32_t header[] = { 0xfeedfacf, 0x100000c, 0, 2, 1, 24, 0, 0, 0x1b, 24 };
    const unsigned char uuid[] = { 0x35,0xcd,0x2e,0x50,0x2d,0x78,0x3a,0x63,0x83,0x5b,0x3e,0xb1,0x22,0x4c,0x6d,0x65 };
    memset(imageHeader, 0, sizeof(imageHeader));
    memcpy(imageHeader, header, sizeof(header));
    memcpy(imageHeader + sizeof(header), uuid, sizeof(uuid));
    unreadableAddress = 0;
}

static void testTargetProfile(void) {
    setupImage();
    const char *stage = NULL;
    assert(configureImage(imageBase, readImage, NULL, &stage) == 0);
    LuaAPI acceptedAPI = api;
    Layout acceptedLayout = layout;
    imageHeader[0] ^= 1;
    assert(configureImage(imageBase, readImage, NULL, &stage) == INSTALL_TARGET_HEADER);
    imageHeader[0] ^= 1;
    imageHeader[40] ^= 1;
    assert(configureImage(imageBase, readImage, NULL, &stage) == INSTALL_TARGET_UUID);
    imageHeader[40] ^= 1;
    uint32_t malformed = 4;
    memcpy(imageHeader + 36, &malformed, sizeof(malformed));
    assert(configureImage(imageBase, readImage, NULL, &stage) == INSTALL_TARGET_HEADER);
    malformed = 24; memcpy(imageHeader + 36, &malformed, sizeof(malformed));
    assert(configureImage(0, readImage, NULL, &stage) == INSTALL_TARGET_HEADER);
    assert(configureImage(UINTPTR_MAX, readImage, NULL, &stage) == INSTALL_TARGET_HEADER);
    for (size_t index = 0; index < sizeof(imagePrefixes)/sizeof(imagePrefixes[0]); ++index) {
        brokenPrefix = (int)index;
        int expected = index ? INSTALL_LUA_BINDING_BASE - (int)index + 1 : INSTALL_UNIT_BINDING;
        assert(configureImage(imageBase, readImage, NULL, &stage) == expected);
        assert(strstr(MGTNativeEffectQueryStatusMessage(expected), "binding mismatch"));
        assert(!memcmp(&api, &acceptedAPI, sizeof(api)) && !memcmp(&layout, &acceptedLayout, sizeof(layout)));
        brokenPrefix = -1;
        unreadablePrefix = (int)index;
        expected = index ? INSTALL_LUA_UNREADABLE_BASE - (int)index + 1 : INSTALL_UNIT_UNREADABLE;
        assert(configureImage(imageBase, readImage, NULL, &stage) == expected);
        assert(strstr(MGTNativeEffectQueryStatusMessage(expected), "unreadable"));
        assert(!memcmp(&api, &acceptedAPI, sizeof(api)) && !memcmp(&layout, &acceptedLayout, sizeof(layout)));
        unreadablePrefix = -1;
    }
    assert(strstr(MGTNativeEffectQueryStatusMessage(-999), "unknown rejection"));
}

static void imageWord(size_t offset, uint32_t value) { memcpy(imageHeader + offset, &value, sizeof(value)); }

static void testProfileValidation(void) {
    const char *stages[] = { "header_read", "header_magic", "header_cpu", "header_filetype",
        "header_table_size", "command_boundary", "command_read", "command_length_small",
        "command_length_boundary", "uuid_length", "uuid_read" };
    setupImage();
    const char *stage = NULL;
    assert(configureImage(imageBase, readImage, NULL, &stage) == 0);
    LuaAPI acceptedAPI = api;
    Layout acceptedLayout = layout;
    for (size_t index = 0; index < sizeof(stages)/sizeof(stages[0]); ++index) {
        setupImage();
        switch (index) {
            case 0: unreadableAddress = imageBase; break;
            case 1: imageWord(0, 0); break;
            case 2: imageWord(4, 0x1000007); break;
            case 3: imageWord(12, 6); break;
            case 4: imageWord(20, 65537); break;
            case 5: imageWord(20, 4); break;
            case 6: unreadableAddress = imageBase + 32; break;
            case 7: imageWord(36, 4); break;
            case 8: imageWord(36, 32); break;
            case 9: imageWord(36, 16); break;
            case 10: unreadableAddress = imageBase + 40; break;
        }
        assert(configureImage(imageBase, readImage, NULL, &stage) == INSTALL_TARGET_HEADER);
        assert(!strcmp(stage, stages[index]));
        assert(!memcmp(&api, &acceptedAPI, sizeof(api)) && !memcmp(&layout, &acceptedLayout, sizeof(layout)));
    }
    /* Traverse a real-sized segment before LC_UUID, and preserve the accepted
     * callback bindings if a later command or UUID cannot be read. */
    setupImage();
    memmove(imageHeader + 104, imageHeader + 32, 24);
    memset(imageHeader + 32, 0, 72);
    imageWord(16, 2); imageWord(20, 96);
    imageWord(32, 0x19); imageWord(36, 72);
    assert(configureImage(imageBase, readImage, NULL, &stage) == 0);
    unreadableAddress = imageBase + 104;
    assert(configureImage(imageBase, readImage, NULL, &stage) == INSTALL_TARGET_HEADER);
    assert(!strcmp(stage, "command_read"));
    assert(!memcmp(&api, &acceptedAPI, sizeof(api)) && !memcmp(&layout, &acceptedLayout, sizeof(layout)));
    unreadableAddress = imageBase + 112;
    assert(configureImage(imageBase, readImage, NULL, &stage) == INSTALL_TARGET_HEADER);
    assert(!strcmp(stage, "uuid_read"));
    assert(!memcmp(&api, &acceptedAPI, sizeof(api)) && !memcmp(&layout, &acceptedLayout, sizeof(layout)));
    assert(configureImage(0, readImage, NULL, &stage) == INSTALL_TARGET_HEADER);
    assert(!strcmp(stage, "base"));
#ifdef __APPLE__
    assert(configureImage(1, readSelf, NULL, &stage) == INSTALL_TARGET_HEADER);
    assert(!strcmp(stage, "header_read"));
#endif
}

static int rejectStack(lua_State *state, int extra) { (void)state; (void)extra; return 0; }

static void *allocator(void *ud, void *ptr, size_t old, size_t size) {
    (void)ud;
    if (!size) { free(ptr); return NULL; }
    ++allocations;
    if (failGrowth && (!ptr || size > old)) return NULL;
    void *p = realloc(ptr, size);
    return (!p && ptr && size <= old) ? ptr : p;
}
static void *findFixtureUnit(void *world, int32_t id) {
    assert(world == (void *)0x1234);
    return id == 7 ? fixtureUnit : NULL;
}
static int readFixture(uintptr_t address, void *destination, size_t size, void *context) {
    (void)context;
    const struct { void *address; size_t size; } regions[] = {
        { fixtureUnit, sizeof(fixtureUnit) }, { &fixtureWorld, sizeof(fixtureWorld) },
        { fixtureBuckets, sizeof(fixtureBuckets) }, { fixtureNames, sizeof(fixtureNames) },
        { &fixtureStrings, sizeof(fixtureStrings) },
        { &fixtureStringLength, sizeof(fixtureStringLength) }, { nodes, sizeof(nodes) },
    };
    for (size_t i = 0; i < sizeof(regions)/sizeof(regions[0]); ++i) {
        uintptr_t start = (uintptr_t)regions[i].address;
        if (address >= start && address - start <= regions[i].size
            && size <= regions[i].size - (address - start)) {
            memcpy(destination, (void *)address, size);
            return 1;
        }
    }
    return 0;
}
static void setCount(uint64_t count) { memcpy(fixtureUnit + 0x780, &count, sizeof(count)); }
static void setup(void) {
    uint32_t type = 0x111, buckets = 2;
    int32_t id = 7;
    uintptr_t pointer = (uintptr_t)fixtureBuckets;
    memset(fixtureUnit, 0, sizeof(fixtureUnit));
    memcpy(fixtureUnit + 8, &type, 4); memcpy(fixtureUnit + 0x48, &id, 4);
    memcpy(fixtureUnit + 0x770, &pointer, sizeof(pointer));
    memcpy(fixtureUnit + 0x778, &buckets, 4);
    fixtureBuckets[0] = 0; fixtureBuckets[1] = 0; fixtureBuckets[2] = UINTPTR_MAX;
    layout = (Layout){ (uintptr_t)&fixtureWorld, (uintptr_t)&fixtureStrings, fixtureStrings,
        (uintptr_t)&fixtureStringLength, findFixtureUnit };
#define WIRE(result, name, args, rva, prefix) api.name = lua_##name;
    LUA_APIS(WIRE)
#undef WIRE
}
int main(void) {
    testTargetProfile();
    testProfileValidation();
    setup();
    Snapshot snapshot;
    assert(collect(&layout, readFixture, NULL, 7, &snapshot) == 1 && snapshot.count == 0);
    fixtureBuckets[0] = (uintptr_t)&nodes[0];
    nodes[0].next = (uintptr_t)&nodes[1]; nodes[1].guid = 11; setCount(2);
    unsigned char before[sizeof(fixtureUnit)]; memcpy(before, fixtureUnit, sizeof(before));
    assert(collect(&layout, readFixture, NULL, 7, &snapshot) == 1 && snapshot.count == 2);
    assert(!strcmp(snapshot.names[0], "StasisStun") && !strcmp(snapshot.names[1], "Inked"));
    assert(!memcmp(before, fixtureUnit, sizeof(before)));
#ifdef __APPLE__
    assert(collect(&layout, readSelf, NULL, 7, &snapshot) == 1 && snapshot.count == 2);
#endif
    setCount(3); assert(collect(&layout, readFixture, NULL, 7, &snapshot) == -1);
    setCount(2); nodes[1].next = (uintptr_t)&nodes[0];
    assert(collect(&layout, readFixture, NULL, 7, &snapshot) == -1); nodes[1].next = 0;
    fixtureBuckets[0] = 1; assert(collect(&layout, readFixture, NULL, 7, &snapshot) == -1);
#ifdef __APPLE__
    assert(collect(&layout, readSelf, NULL, 7, &snapshot) == -1);
#endif
    fixtureBuckets[0] = (uintptr_t)&nodes[0]; nodes[1].guid = fixtureStringLength;
    assert(collect(&layout, readFixture, NULL, 7, &snapshot) == -1); nodes[1].guid = 11;
    memset(fixtureNames, 'a', sizeof(fixtureNames)); fixtureStringLength = sizeof(fixtureNames);
    assert(collect(&layout, readFixture, NULL, 7, &snapshot) == -1);
    memcpy(fixtureNames, "StasisStun\0Inked", 17); fixtureStringLength = 17;
    ++fixtureStrings; assert(collect(&layout, readFixture, NULL, 7, &snapshot) == -1); --fixtureStrings;
    setCount(MAX_BLOCKS + 1); assert(collect(&layout, readFixture, NULL, 7, &snapshot) == -1); setCount(2);
    uint32_t hugeBuckets = MAX_BUCKETS + 1;
    memcpy(fixtureUnit + 0x778, &hugeBuckets, 4);
    assert(collect(&layout, readFixture, NULL, 7, &snapshot) == -1);
    hugeBuckets = 2; memcpy(fixtureUnit + 0x778, &hugeBuckets, 4);
    uintptr_t token = 0;
    assert(unitIdentity(&layout, readFixture, NULL, 8, &token) == 0);
    fixtureWorld = 0; assert(unitIdentity(&layout, readFixture, NULL, 7, &token) == 0); fixtureWorld = 0x1234;
    int32_t id = 8; memcpy(fixtureUnit + 0x48, &id, 4);
    assert(unitIdentity(&layout, readFixture, NULL, 7, &token) == -1);
    id = 7; memcpy(fixtureUnit + 0x48, &id, 4);

    lua_State *L = lua_newstate(allocator, NULL); assert(L);
    assert(MGTNativeEffectQueryABI() == 3);
    uintptr_t mainBase = 0;
#ifdef __APPLE__
    extern const struct mach_header_64 _mh_execute_header;
    mainBase = (uintptr_t)&_mh_execute_header;
    if (getenv("MGT_EXPECT_STARTUP_IMAGE")) {
        assert((uintptr_t)_dyld_get_image_header(0) != mainBase);
        assert(_dyld_get_image_header(0)->filetype == MH_DYLIB);
    }
#endif
    char diagnostic[256];
    int rejected = MGTNativeEffectQueryInstall(L, mainBase, diagnostic, sizeof(diagnostic));
    assert(rejected < 0 && lua_gettop(L) == 0);
#if defined(__APPLE__) && defined(__arm64__)
    assert(rejected == INSTALL_TARGET_UUID); /* Header selection reaches the correct helper main; it is not Hades. */
    assert(strstr(diagnostic, "UUID") && strstr(diagnostic, "uuid_mismatch"));
    if (getenv("MGT_EXPECT_STARTUP_IMAGE")) printf("native_image_selection_ok: status=%d %s\n", rejected, diagnostic);
    char tiny[] = {'x','!'};
    assert(MGTNativeEffectQueryInstall(L, mainBase, tiny, 1) == rejected && tiny[0] == 0 && tiny[1] == '!');
    assert(MGTNativeEffectQueryInstall(L, mainBase, NULL, 0) == rejected);
    assert(MGTNativeEffectQueryInstall(L, 0, diagnostic, sizeof(diagnostic)) == INSTALL_TARGET_HEADER);
    assert(strstr(diagnostic, "header") && strstr(diagnostic, "(base)"));
#endif
    assert(strcmp(MGTNativeEffectQueryStatusMessage(rejected),
        "Native query registration returned an unknown rejection status") != 0);
    lua_pushinteger(L, 42);
    api.checkstack = rejectStack;
    assert(installQueries(L) == INSTALL_STACK_UNAVAILABLE && lua_gettop(L) == 1);
    assert(strstr(MGTNativeEffectQueryStatusMessage(INSTALL_STACK_UNAVAILABLE), "Lua stack"));
    api.checkstack = lua_checkstack;
    assert(installQueries(L) == LUA_OK && lua_gettop(L) == 1 && lua_tointeger(L, 1) == 42);
    lua_getglobal(L, "__MGTHadesNativeV1"); lua_getfield(L, -1, "abi");
    assert(lua_tointeger(L, -1) == 1); /* Lua callback contract is unchanged. */
    lua_pop(L, 2);
    lua_settop(L, 0);
    lua_getglobal(L, "__MGTHadesNativeV1"); lua_getfield(L, -1, "unitIdentity");
    lua_remove(L, -2); /* Keep a callback even after the namespace is replaced. */
    lua_pushnil(L); lua_setglobal(L, "__MGTHadesNativeV1");
    assert(installQueries(L) == LUA_OK && lua_gettop(L) == 1);
    lua_pushinteger(L, 7); assert(lua_pcall(L, 1, LUA_MULTRET, 0) == LUA_OK);
#ifdef __APPLE__
    assert(lua_gettop(L) == 1 && lua_touserdata(L, 1) == fixtureUnit);
#else
    assert(lua_gettop(L) == 2 && lua_isnil(L, 1) && lua_isstring(L, 2));
#endif
    lua_settop(L, 0);
    lua_gc(L, LUA_GCSTOP, 0); assert(lua_checkstack(L, 2));
    size_t start = allocations; lua_pushcclosure(L, registerQueries, 0);
    assert(allocations == start); lua_pop(L, 1);
    failGrowth = 1; int status = installQueries(L); failGrowth = 0;
    assert(status == LUA_ERRMEM && lua_gettop(L) == 1 && lua_type(L, -1) == LUA_TSTRING);
    lua_settop(L, 0);
    int32_t parsed = 0;
    lua_pushinteger(L, 7); assert(objectId(L, &parsed) && parsed == 7); lua_settop(L, 0);
    const double invalid[] = { 7.5, NAN, INFINITY, 0, -1, (double)INT32_MAX + 1 };
    for (size_t i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        lua_pushnumber(L, invalid[i]); assert(!objectId(L, &parsed)); lua_settop(L, 0);
    }
    lua_pushliteral(L, "7"); assert(!objectId(L, &parsed));
    lua_close(L);
    puts("native_effect_query_ok: verified image authority, bounded failure, full profile, set, identity, bounds, stack, OOM, retained callback");
    return 0;
}
