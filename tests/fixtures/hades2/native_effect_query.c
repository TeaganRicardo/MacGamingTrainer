/* Exercise the actual private C implementation; no game process is involved. */
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
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
    assert(MGTNativeEffectQueryABI() == 1);
    assert(MGTNativeEffectQueryInstall(L) == -1 && lua_gettop(L) == 0);
    lua_pushinteger(L, 42);
    assert(installQueries(L) == LUA_OK && lua_gettop(L) == 1 && lua_tointeger(L, 1) == 42);
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
    puts("native_effect_query_ok: set, identity, read errors, bounds, UUID rejection, stack, OOM, retained callback");
    return 0;
}
