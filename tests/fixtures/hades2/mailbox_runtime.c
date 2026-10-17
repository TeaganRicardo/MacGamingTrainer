/* Exercise the production consumer against real Lua 5.2 and temporary slots.
 * Only the platform rendezvous/code patch is replaced; no game is launched. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"

static int fixture_main_thread = 1;
static int fixtureMainThread(void) { return fixture_main_thread; }
#define pthread_main_np fixtureMainThread
#define MGT_MAILBOX_RUNTIME_TEST 1
#include "CommandMailbox.c"

static lua_State *fixture_state;
static unsigned query_calls, gettop_calls, tostring_calls;
static int query_status, fail_growth;
static uint64_t generation;

static void *allocateLua(void *context, void *pointer, size_t old_size, size_t size) {
    (void)context;
    if (size == 0) { free(pointer); return NULL; }
    if (fail_growth && (pointer == NULL || size > old_size)) return NULL;
    return realloc(pointer, size);
}

static int countGettop(lua_State *state) { ++gettop_calls; return lua_gettop(state); }
static const char *countTostring(lua_State *state, int index, size_t *length) {
    ++tostring_calls;
    return lua_tolstring(state, index, length);
}
static int queryInstaller(lua_State *state, uintptr_t base, char *output, size_t capacity) {
    (void)state; (void)base;
    ++query_calls;
    if (query_status) snprintf(output, capacity, "fixture native query unavailable");
    return query_status;
}

static void freshProcess(void) {
    if (active_lease.slot) free(active_lease.slot);
    if (fixture_state) lua_close(fixture_state);
    memset(&active_lease, 0, sizeof(active_lease));
    process_tainted = 0;
    in_pump = installing = fail_growth = query_status = 0;
    fixture_main_thread = 1;
    fixture_state = lua_newstate(allocateLua, NULL);
    assert(fixture_state);
    luaL_openlibs(fixture_state);
    lua = (LuaAPI){
        .gettop = countGettop, .settop = lua_settop, .checkstack = lua_checkstack,
        .type = lua_type, .tolstring = countTostring, .pushlstring = lua_pushlstring,
        .pushcclosure = lua_pushcclosure, .pushlightuserdata = lua_pushlightuserdata,
        .rawget = lua_rawget, .rawset = lua_rawset, .loadbufferx = luaL_loadbufferx,
        .pcallk = lua_pcallk,
    };
    /* The same indirection as ScriptManager::LuaInterface, without an image. */
    image_base = (uintptr_t)&fixture_state - LUA_INTERFACE_RVA;
    MGTMailboxSlot *slot = calloc(1, sizeof(*slot));
    assert(slot && mgt_mailbox_init(slot, 0x1234, ++generation,
                                    (uint32_t)getpid(), (uint32_t)getpid()) == MGT_MAILBOX_OK);
    active_lease = (MailboxLease){ slot, fixture_state, 0x1234, generation, queryInstaller };
    lua_pushliteral(fixture_state, "stack sentinel");
    assert(bindGeneration(&active_lease) == LUA_OK);
    assert(generationMatches(&active_lease));
    gettop_calls = tostring_calls = query_calls = 0;
}

static void submit(const char *source) {
    MGTMailboxSlot *slot = active_lease.slot;
    uint64_t sequence = atomic_load_explicit(&slot->highest_sequence, memory_order_relaxed) + 1;
    assert(mgt_mailbox_submit(slot, active_lease.hi, active_lease.lo, sequence,
                              source, strlen(source)) == MGT_MAILBOX_OK);
}

static MGTMailboxReceipt receipt(uint32_t outcome, int status, char *output, size_t capacity) {
    MGTMailboxSlot *slot = active_lease.slot;
    MGTMailboxReceipt result;
    assert(mgt_mailbox_read(slot, active_lease.hi, active_lease.lo, slot->sequence,
                            &result, output, capacity) == MGT_MAILBOX_OK);
    assert(result.outcome == outcome && result.status == status);
    assert(result.length <= capacity);
    if (result.length < capacity) output[result.length] = 0;
    assert(lua_gettop(fixture_state) == 1);
    assert(strcmp(lua_tostring(fixture_state, 1), "stack sentinel") == 0);
    return result;
}

static void acknowledge(void) {
    MGTMailboxSlot *slot = active_lease.slot;
    assert(mgt_mailbox_ack(slot, active_lease.hi, active_lease.lo, slot->sequence) == MGT_MAILBOX_OK);
}

static pid_t exitedProducer(void) {
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) _exit(0);
    int status;
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status));
    assert(!producerAlive((uint32_t)child));
    return child;
}

static void testIdleAndMainThread(void) {
    freshProcess();
    for (unsigned index = 0; index < 1000; ++index) mgtCommandMailboxPump();
    assert(gettop_calls == 0 && tostring_calls == 0 && query_calls == 0);
    assert(atomic_load(&active_lease.slot->heartbeat_count) == 1000);
    submit("marker = (marker or 0) + 1; return 'completed'");
    fixture_main_thread = 0;
    mgtCommandMailboxPump();
    assert(mgt_mailbox_state(active_lease.slot) == MGT_MAILBOX_POSTED && query_calls == 0);
    fixture_main_thread = 1;
    mgtCommandMailboxPump();
    char output[256];
    receipt(MGT_MAILBOX_SUCCESS, 0, output, sizeof(output));
    assert(strcmp(output, "completed") == 0 && query_calls == 1);
    mgtCommandMailboxPump(); /* A complete, unacknowledged command cannot run twice. */
    assert(query_calls == 1);
    lua_getglobal(fixture_state, "marker");
    assert(lua_tointeger(fixture_state, -1) == 1); lua_pop(fixture_state, 1);
    acknowledge();
}

static void testGeneration(void) {
    char output[256];
    freshProcess();
    lua.pushlightuserdata(fixture_state, &registry_key);
    lua_pushnil(fixture_state); lua_rawset(fixture_state, LUA_REGISTRYINDEX);
    submit("marker = 1; return 'must not execute'");
    mgtCommandMailboxPump();
    receipt(MGT_MAILBOX_ERROR, GENERATION_CHANGED, output, sizeof(output));
    assert(query_calls == 0 && mgt_mailbox_flags(active_lease.slot) == MGT_MAILBOX_CLOSED_FLAG);
    assert(!process_tainted);
    /* The rejected source never ran; a dead/recovering producer need not ACK. */
    assert(canRetireLease(output, sizeof(output)) == 0);
    lua_getglobal(fixture_state, "marker"); assert(lua_isnil(fixture_state, -1)); lua_pop(fixture_state, 1);

    freshProcess();
    lua_State *original = fixture_state;
    fixture_state = luaL_newstate(); assert(fixture_state);
    submit("return 'must not execute on replacement VM'");
    mgtCommandMailboxPump();
    assert(query_calls == 0 && gettop_calls == 0 && lua_gettop(fixture_state) == 0);
    lua_close(fixture_state); fixture_state = original;
    receipt(MGT_MAILBOX_ERROR, GENERATION_CHANGED, output, sizeof(output));
    acknowledge();
}

static void testErrorsAndBounds(void) {
    char output[512];
    freshProcess();
    submit("error('known Lua refusal')"); mgtCommandMailboxPump();
    receipt(MGT_MAILBOX_ERROR, LUA_ERRRUN, output, sizeof(output));
    assert(strstr(output, "known Lua refusal") && !process_tainted);
    acknowledge();
    submit("syntax is not valid Lua!"); mgtCommandMailboxPump();
    receipt(MGT_MAILBOX_ERROR, LUA_ERRSYNTAX, output, sizeof(output));
    assert(!process_tainted); acknowledge();
    query_status = -42;
    submit("marker = 1; return 'must not execute'"); mgtCommandMailboxPump();
    receipt(MGT_MAILBOX_ERROR, -42, output, sizeof(output));
    assert(strstr(output, "native query unavailable") && !process_tainted);
    acknowledge();

    freshProcess();
    submit("return 123"); mgtCommandMailboxPump();
    /* Only registry's known string was converted. Result-number conversion
     * would allocate outside pcall; the consumer must reject it first. */
    assert(tostring_calls == 1);
    receipt(MGT_MAILBOX_UNKNOWN, 0, output, sizeof(output));
    assert(process_tainted && mgt_mailbox_flags(active_lease.slot) == MGT_MAILBOX_LEASE_FLAGS);

    freshProcess();
    submit("return string.rep('x', 262144)"); mgtCommandMailboxPump();
    char *maximum = malloc(MGT_MAILBOX_RESULT_CAPACITY); assert(maximum);
    MGTMailboxReceipt exact = receipt(MGT_MAILBOX_SUCCESS, 0, maximum, MGT_MAILBOX_RESULT_CAPACITY);
    assert(exact.length == MGT_MAILBOX_RESULT_CAPACITY && maximum[0] == 'x'
           && maximum[MGT_MAILBOX_RESULT_CAPACITY - 1] == 'x');
    free(maximum); acknowledge();
    submit("return string.rep('x', 262145)"); mgtCommandMailboxPump();
    receipt(MGT_MAILBOX_UNKNOWN, 0, output, sizeof(output));
    assert(process_tainted && strstr(output, "capacity"));
}

static void testLeaseRecovery(void) {
    char output[256];
    freshProcess();
    assert(canRetireLease(output, sizeof(output)) == INSTALL_FAILURE);
    assert(mgt_mailbox_flags(active_lease.slot) == 0 && !process_tainted);
    active_lease.slot->producer_pid = (uint32_t)exitedProducer();
    assert(canRetireLease(output, sizeof(output)) == 0 && !process_tainted);
    assert(mgt_mailbox_flags(active_lease.slot) == MGT_MAILBOX_CLOSED_FLAG);

    freshProcess();
    active_lease.slot->producer_pid = (uint32_t)exitedProducer();
    submit("marker = 1; return 'must not execute after producer death'");
    mgtCommandMailboxPump();
    receipt(MGT_MAILBOX_CANCELLED, 0, output, sizeof(output));
    assert(query_calls == 0 && atomic_load(&active_lease.slot->claimed_count) == 0);
    assert(!process_tainted);
    assert(canRetireLease(output, sizeof(output)) == 0 && !process_tainted);

    freshProcess();
    submit("return 'cancelled before execution'");
    assert(mgt_mailbox_cancel(active_lease.slot, active_lease.hi, active_lease.lo,
                              active_lease.slot->sequence) == MGT_MAILBOX_OK);
    assert(canRetireLease(output, sizeof(output)) == INSTALL_FAILURE && !process_tainted);
    mgt_mailbox_close(active_lease.slot, active_lease.hi, active_lease.lo);
    assert(canRetireLease(output, sizeof(output)) == 0 && !process_tainted);

    freshProcess();
    submit("return 'received but not acknowledged'"); mgtCommandMailboxPump();
    receipt(MGT_MAILBOX_SUCCESS, 0, output, sizeof(output));
    assert(canRetireLease(output, sizeof(output)) == INSTALL_FAILURE && !process_tainted);
    mgt_mailbox_close(active_lease.slot, active_lease.hi, active_lease.lo);
    assert(canRetireLease(output, sizeof(output)) == INSTALL_RESTART_REQUIRED && process_tainted);
    /* Even acknowledging later cannot erase process-level uncertainty. */
    acknowledge();
    assert(canRetireLease(output, sizeof(output)) == INSTALL_RESTART_REQUIRED);

    freshProcess();
    submit("error('ordinary Lua failure')"); mgtCommandMailboxPump();
    receipt(MGT_MAILBOX_ERROR, LUA_ERRRUN, output, sizeof(output));
    mgt_mailbox_close(active_lease.slot, active_lease.hi, active_lease.lo);
    assert(canRetireLease(output, sizeof(output)) == INSTALL_RESTART_REQUIRED && process_tainted);
}

static void testProtectedRegistryAllocation(void) {
    freshProcess();
    MailboxLease candidate = active_lease;
    candidate.lo += 1000; /* A new binary string must be allocated. */
    lua_gc(fixture_state, LUA_GCSTOP, 0);
    assert(lua_checkstack(fixture_state, 8));
    fail_growth = 1;
    int status = bindGeneration(&candidate);
    fail_growth = 0;
    assert(status == LUA_ERRMEM);
    assert(lua_gettop(fixture_state) == 1 && generationMatches(&active_lease));
    assert(installing_lease == NULL);
}

int main(void) {
    testIdleAndMainThread();
    testGeneration();
    testErrorsAndBounds();
    testLeaseRecovery();
    testProtectedRegistryAllocation();
    free(active_lease.slot); active_lease.slot = NULL;
    lua_close(fixture_state); fixture_state = NULL;
    puts("mailbox_runtime_ok: idle/main-thread, exactly-once claim, Lua stack/errors/bounds, registry generation/OOM, producer death, unacknowledged lease");
    return 0;
}
