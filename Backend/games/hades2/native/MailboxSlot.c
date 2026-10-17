/* Experimental Hades II mailbox slot. Not installed in the game or packaged.
 * Memory must be MAP_SHARED across producer/consumer processes.
 * The host is the only producer; the game main thread is the only pump.
 * No recovery code may reset an in-flight slot after an unknown outcome. */
#include <stdint.h>
#include <stddef.h>
#include <stdatomic.h>
#include <string.h>
#ifdef __APPLE__
#include <pthread.h>
#endif

#define MGT_EXPORT __attribute__((visibility("default")))
#define MGT_MAILBOX_MAGIC 0x4d47544du
#define MGT_MAILBOX_ABI 1u
/* LLDB retains ownership of large resident bootstrap source installation. */
#define MGT_INPUT_LIMIT 65536u
/* Match the existing Hades Lua result budget, without silently expanding it. */
#define MGT_OUTPUT_LIMIT 262144u

enum { MGT_IDLE=0, MGT_RESERVING=1, MGT_POSTED=2, MGT_EXECUTING=3, MGT_COMPLETE=4 };
enum { MGT_SUCCESS=0, MGT_KNOWN_FAILED=1, MGT_OUTCOME_UNKNOWN=2 };

typedef struct {
    uint32_t magic, abi;
    uint64_t generation_hi, generation_lo;
    _Atomic uint32_t phase;
    _Atomic uint32_t receipt_read;
    uint32_t input_len, output_len, outcome;
    uint64_t request_id, last_accepted_id;
    unsigned char input[MGT_INPUT_LIMIT];
    unsigned char output[MGT_OUTPUT_LIMIT];
} MGTMailboxSlot;

typedef uint32_t (*MGTMailboxHandler)(const void *, uint32_t, void *, uint32_t, uint32_t *, void *);

static int valid(const MGTMailboxSlot *slot, uint64_t hi, uint64_t lo) {
    return slot && slot->magic == MGT_MAILBOX_MAGIC && slot->abi == MGT_MAILBOX_ABI
        && slot->generation_hi == hi && slot->generation_lo == lo
        && (hi != 0 || lo != 0);
}

MGT_EXPORT uint32_t MGTMailboxABI(void) { return MGT_MAILBOX_ABI; }
MGT_EXPORT size_t MGTMailboxSize(void) { return sizeof(MGTMailboxSlot); }
MGT_EXPORT int MGTMailboxInit(void *buffer, size_t bytes, uint64_t hi, uint64_t lo) {
    if (!buffer || bytes < sizeof(MGTMailboxSlot) || (hi == 0 && lo == 0))
        return -1;
    if (((uintptr_t)buffer % _Alignof(MGTMailboxSlot)) != 0) return -2;
    MGTMailboxSlot *slot = (MGTMailboxSlot *)buffer;
    /* Creating another generation over a potentially executing request
     * silently loses its receipt. A new session requires a fresh mapping. */
    if (slot->magic != 0 || slot->abi != 0) return -3;
    memset(slot, 0, sizeof(*slot));
    slot->generation_hi = hi;
    slot->generation_lo = lo;
    atomic_init(&slot->phase, MGT_IDLE);
    atomic_init(&slot->receipt_read, 0);
    slot->abi = MGT_MAILBOX_ABI;
    slot->magic = MGT_MAILBOX_MAGIC;
    return 0;
}
MGT_EXPORT uint32_t MGTMailboxPhase(void *buffer, uint64_t hi, uint64_t lo) {
    MGTMailboxSlot *slot = (MGTMailboxSlot *)buffer;
    if (!valid(slot, hi, lo)) return UINT32_MAX;
    return atomic_load_explicit(&slot->phase, memory_order_acquire);
}
MGT_EXPORT int MGTMailboxSubmit(void *buffer, uint64_t hi, uint64_t lo,
                                uint64_t id, const void *input, uint32_t length) {
    MGTMailboxSlot *slot = (MGTMailboxSlot *)buffer;
    if (!valid(slot, hi, lo) || !id || !input || !length || length > MGT_INPUT_LIMIT)
        return -1;
    uint32_t expected = MGT_IDLE;
    if (!atomic_compare_exchange_strong_explicit(
            &slot->phase, &expected, MGT_RESERVING,
            memory_order_acq_rel, memory_order_acquire)) return -2;
    /* last_accepted_id survives acknowledgement. A previously crossed
     * request ID must never execute again, even if its reply was lost. */
    if (id <= slot->last_accepted_id) {
        atomic_store_explicit(&slot->phase, MGT_IDLE, memory_order_release);
        return -3;
    }
    memcpy(slot->input, input, length);
    slot->input_len = length;
    atomic_store_explicit(&slot->receipt_read, 0, memory_order_relaxed);
    slot->output_len = 0;
    slot->outcome = MGT_OUTCOME_UNKNOWN;
    slot->request_id = id;
    slot->last_accepted_id = id;
    atomic_store_explicit(&slot->phase, MGT_POSTED, memory_order_release);
    return 0;
}
MGT_EXPORT int MGTMailboxPump(void *buffer, uint64_t hi, uint64_t lo,
                              MGTMailboxHandler handler, void *context) {
    MGTMailboxSlot *slot = (MGTMailboxSlot *)buffer;
    if (!valid(slot, hi, lo) || !handler) return -1;
#ifdef __APPLE__
    /* Darwin main-thread ownership is a native execution requirement, not
     * a promise made by whichever transport happened to invoke this symbol. */
    if (!pthread_main_np()) return -3;
#endif
    uint32_t expected = MGT_POSTED;
    if (!atomic_compare_exchange_strong_explicit(
            &slot->phase, &expected, MGT_EXECUTING,
            memory_order_acq_rel, memory_order_acquire)) return 0;
    /* This callback MUST be invoked only from the verified game main thread.
     * No locks, waits, I/O or background-thread Lua calls occur in this slot. */
    uint32_t length = 0;
    uint32_t outcome = handler(slot->input, slot->input_len,
                               slot->output, MGT_OUTPUT_LIMIT, &length, context);
    if (length > MGT_OUTPUT_LIMIT || outcome > MGT_OUTCOME_UNKNOWN) {
        /* Execution may already have mutated native state: overflow or
         * malformed receipts are UNKNOWN, never a retryable failure. */
        outcome = MGT_OUTCOME_UNKNOWN;
        length = 0;
    }
    slot->output_len = length;
    slot->outcome = outcome;
    atomic_store_explicit(&slot->phase, MGT_COMPLETE, memory_order_release);
    return 1;
}
MGT_EXPORT int MGTMailboxRead(void *buffer, uint64_t hi, uint64_t lo,
                              uint64_t id, void *output, uint32_t capacity,
                              uint32_t *length, uint32_t *outcome) {
    MGTMailboxSlot *slot = (MGTMailboxSlot *)buffer;
    if (!valid(slot, hi, lo) || !output || !length || !outcome)
        return -1;
    if (atomic_load_explicit(&slot->phase, memory_order_acquire) != MGT_COMPLETE
        || slot->request_id != id || !id) return -2;
    if (slot->output_len > capacity || slot->output_len > MGT_OUTPUT_LIMIT)
        return -3;
    memcpy(output, slot->output, slot->output_len);
    *length = slot->output_len;
    *outcome = slot->outcome;
    /* Ack requires that the full receipt has crossed into the producer. */
    atomic_store_explicit(&slot->receipt_read, 1, memory_order_release);
    return 0;
}
MGT_EXPORT int MGTMailboxAck(void *buffer, uint64_t hi, uint64_t lo,
                             uint64_t id) {
    MGTMailboxSlot *slot = (MGTMailboxSlot *)buffer;
    if (!valid(slot, hi, lo) || !id) return -1;
    if (atomic_load_explicit(&slot->phase, memory_order_acquire) != MGT_COMPLETE)
        return -2;
    if (slot->request_id != id) return -1;
    /* An unknown native outcome poisons this entire generation. It cannot
     * be cleared by a normal acknowledgment or automatic route fallback. */
    if (slot->outcome == MGT_OUTCOME_UNKNOWN
        || atomic_load_explicit(&slot->receipt_read, memory_order_acquire) != 1)
        return -3;
    uint32_t expected = MGT_COMPLETE;
    if (!atomic_compare_exchange_strong_explicit(
            &slot->phase, &expected, MGT_IDLE,
            memory_order_acq_rel, memory_order_acquire)) return -2;
    /* Preserve request_id/last_accepted_id as durable in-generation evidence.
     * Never ack a request merely because a transport timeout elapsed. */
    return 0;
}
