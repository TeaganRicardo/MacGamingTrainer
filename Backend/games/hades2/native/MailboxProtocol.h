#ifndef MGT_HADES2_MAILBOX_PROTOCOL_H
#define MGT_HADES2_MAILBOX_PROTOCOL_H

/* One serialized producer and one successful consumer claim per request.
 * Both processes map the same storage. Initialization happens before sharing;
 * the generation and process identities never change within a mapping.
 * Close/poison may race either participant. Mapping lifetime is caller-owned.
 */
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>
#include <string.h>

#define MGT_MAILBOX_ABI 1u
#define MGT_MAILBOX_MAGIC UINT32_C(0x4d47544d)
#define MGT_MAILBOX_SOURCE_CAPACITY UINT32_C(1048576)
#define MGT_MAILBOX_RESULT_CAPACITY UINT32_C(262144)

typedef enum {
    MGT_MAILBOX_OK = 0,
    MGT_MAILBOX_EMPTY = 1,
    MGT_MAILBOX_BUSY = 2,
    MGT_MAILBOX_STALE = 3,
    MGT_MAILBOX_INVALID = 4,
    MGT_MAILBOX_CLOSED = 5,
    MGT_MAILBOX_POISONED = 6,
    MGT_MAILBOX_DUPLICATE = 7,
    MGT_MAILBOX_CAPACITY = 8
} MGTMailboxResult;

typedef enum {
    MGT_MAILBOX_IDLE = 0,
    MGT_MAILBOX_RESERVING = 1,
    MGT_MAILBOX_POSTED = 2,
    MGT_MAILBOX_EXECUTING = 3,
    MGT_MAILBOX_COMPLETE = 4
} MGTMailboxState;

typedef enum {
    MGT_MAILBOX_SUCCESS = 0,
    MGT_MAILBOX_ERROR = 1,
    MGT_MAILBOX_CANCELLED = 2,
    MGT_MAILBOX_UNKNOWN = 3
} MGTMailboxOutcome;

#define MGT_MAILBOX_STATE_MASK UINT32_C(0xff)
#define MGT_MAILBOX_CLOSED_FLAG UINT32_C(0x100)
#define MGT_MAILBOX_POISONED_FLAG UINT32_C(0x200)
#define MGT_MAILBOX_READ_FLAG UINT32_C(0x400)
#define MGT_MAILBOX_LEASE_FLAGS (MGT_MAILBOX_CLOSED_FLAG | MGT_MAILBOX_POISONED_FLAG)

typedef struct {
    uint32_t magic;
    uint32_t abi;
    uint32_t slot_size;
    uint32_t producer_pid;
    uint32_t target_pid;
    uint32_t reserved;
    uint64_t generation_hi;
    uint64_t generation_lo;
    _Atomic uint32_t control;
    _Atomic uint64_t highest_sequence;
    _Atomic uint64_t heartbeat_count;
    _Atomic uint64_t heartbeat_ns;
    _Atomic uint64_t claimed_count;
    _Atomic uint64_t completed_count;
    uint64_t sequence;
    uint32_t source_length;
    uint32_t result_length;
    uint32_t outcome;
    int32_t status;
    uint64_t execution_ns;
    unsigned char source[MGT_MAILBOX_SOURCE_CAPACITY];
    unsigned char result[MGT_MAILBOX_RESULT_CAPACITY];
} MGTMailboxSlot;

typedef struct {
    uint64_t sequence;
    const unsigned char *source;
    size_t length;
} MGTMailboxRequest;

typedef struct {
    uint64_t generation_hi;
    uint64_t generation_lo;
    uint64_t sequence;
    uint32_t outcome;
    int32_t status;
    size_t length;
    uint64_t execution_ns;
} MGTMailboxReceipt;

_Static_assert(sizeof(_Atomic uint32_t) == sizeof(uint32_t), "Mailbox requires a fixed atomic ABI");
_Static_assert(sizeof(_Atomic uint64_t) == sizeof(uint64_t), "Mailbox requires a fixed atomic ABI");
_Static_assert(sizeof(MGTMailboxSlot) < UINT32_MAX, "Mailbox size must fit its ABI header");

static inline uint32_t mgt_mailbox_state(const MGTMailboxSlot *slot) {
    return atomic_load_explicit(&slot->control, memory_order_acquire) & MGT_MAILBOX_STATE_MASK;
}

static inline uint32_t mgt_mailbox_flags(const MGTMailboxSlot *slot) {
    return atomic_load_explicit(&slot->control, memory_order_acquire) & MGT_MAILBOX_LEASE_FLAGS;
}

static inline MGTMailboxResult mgt_mailbox_lease_result(uint32_t control) {
    if (control & MGT_MAILBOX_POISONED_FLAG) return MGT_MAILBOX_POISONED;
    if (control & MGT_MAILBOX_CLOSED_FLAG) return MGT_MAILBOX_CLOSED;
    return MGT_MAILBOX_OK;
}

static inline MGTMailboxResult mgt_mailbox_validate(
    const MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo
) {
    if (slot == NULL || (uintptr_t)slot % _Alignof(MGTMailboxSlot) != 0
        || slot->magic != MGT_MAILBOX_MAGIC || slot->abi != MGT_MAILBOX_ABI
        || slot->slot_size != sizeof(*slot) || slot->producer_pid == 0
        || slot->producer_pid > INT32_MAX || slot->target_pid == 0
        || slot->target_pid > INT32_MAX || slot->reserved != 0
        || (slot->generation_hi == 0 && slot->generation_lo == 0)
        || !atomic_is_lock_free(&slot->control)
        || !atomic_is_lock_free(&slot->highest_sequence)) return MGT_MAILBOX_INVALID;
    if (slot->generation_hi != generation_hi || slot->generation_lo != generation_lo)
        return MGT_MAILBOX_STALE;
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    if ((control & MGT_MAILBOX_STATE_MASK) > MGT_MAILBOX_COMPLETE
        || (control & ~(MGT_MAILBOX_STATE_MASK | MGT_MAILBOX_LEASE_FLAGS | MGT_MAILBOX_READ_FLAG)))
        return MGT_MAILBOX_INVALID;
    return MGT_MAILBOX_OK;
}

/* Call only on new, zeroed, unshared storage; never reset/reopen a mapping. */
static inline MGTMailboxResult mgt_mailbox_init(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo,
    uint32_t producer_pid, uint32_t target_pid
) {
    if (slot == NULL || (uintptr_t)slot % _Alignof(MGTMailboxSlot) != 0
        || (generation_hi == 0 && generation_lo == 0)
        || producer_pid == 0 || producer_pid > INT32_MAX
        || target_pid == 0 || target_pid > INT32_MAX
        || slot->magic != 0 || slot->abi != 0) return MGT_MAILBOX_INVALID;
    memset(slot, 0, sizeof(*slot));
    slot->magic = MGT_MAILBOX_MAGIC;
    slot->abi = MGT_MAILBOX_ABI;
    slot->slot_size = (uint32_t)sizeof(*slot);
    slot->producer_pid = producer_pid;
    slot->target_pid = target_pid;
    slot->generation_hi = generation_hi;
    slot->generation_lo = generation_lo;
    atomic_init(&slot->control, MGT_MAILBOX_IDLE);
    atomic_init(&slot->highest_sequence, 0);
    atomic_init(&slot->heartbeat_count, 0);
    atomic_init(&slot->heartbeat_ns, 0);
    atomic_init(&slot->claimed_count, 0);
    atomic_init(&slot->completed_count, 0);
    return mgt_mailbox_validate(slot, generation_hi, generation_lo);
}

static inline MGTMailboxResult mgt_mailbox_submit(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo,
    uint64_t sequence, const void *source, size_t length
) {
    MGTMailboxResult valid = mgt_mailbox_validate(slot, generation_hi, generation_lo);
    if (valid != MGT_MAILBOX_OK) return valid;
    if (sequence == 0 || (source == NULL && length != 0)) return MGT_MAILBOX_INVALID;
    if (length > MGT_MAILBOX_SOURCE_CAPACITY) return MGT_MAILBOX_CAPACITY;
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    MGTMailboxResult lease = mgt_mailbox_lease_result(control);
    if (lease != MGT_MAILBOX_OK) return lease;
    uint32_t state = control & MGT_MAILBOX_STATE_MASK;
    uint64_t highest = atomic_load_explicit(&slot->highest_sequence, memory_order_acquire);
    if (sequence <= highest) {
        if (state == MGT_MAILBOX_RESERVING) return MGT_MAILBOX_BUSY;
        if (state != MGT_MAILBOX_IDLE && sequence == slot->sequence) {
            if (length != slot->source_length
                || (length != 0 && memcmp(source, slot->source, length) != 0)) return MGT_MAILBOX_INVALID;
            return MGT_MAILBOX_DUPLICATE;
        }
        return MGT_MAILBOX_STALE;
    }
    if (state != MGT_MAILBOX_IDLE) return MGT_MAILBOX_BUSY;
    uint32_t expected = MGT_MAILBOX_IDLE;
    if (!atomic_compare_exchange_strong_explicit(&slot->control, &expected,
            MGT_MAILBOX_RESERVING, memory_order_acquire, memory_order_acquire)) {
        lease = mgt_mailbox_lease_result(expected);
        return lease == MGT_MAILBOX_OK ? MGT_MAILBOX_BUSY : lease;
    }
    if (length != 0) memcpy(slot->source, source, length);
    slot->sequence = sequence;
    slot->source_length = (uint32_t)length;
    slot->result_length = 0;
    slot->outcome = MGT_MAILBOX_UNKNOWN;
    slot->status = 0;
    slot->execution_ns = 0;
    atomic_store_explicit(&slot->highest_sequence, sequence, memory_order_release);
    expected = MGT_MAILBOX_RESERVING;
    if (!atomic_compare_exchange_strong_explicit(&slot->control, &expected,
            MGT_MAILBOX_POSTED, memory_order_release, memory_order_relaxed)) {
        /* A concurrent close/poison prevented publication. No consumer can
         * claim RESERVING, and its immutable lease flags must survive. */
        atomic_fetch_and_explicit(&slot->control, MGT_MAILBOX_LEASE_FLAGS, memory_order_release);
        lease = mgt_mailbox_lease_result(expected);
        return lease == MGT_MAILBOX_OK ? MGT_MAILBOX_INVALID : lease;
    }
    return MGT_MAILBOX_OK;
}

/* Only the owner of the expected state may write a terminal receipt. */
static inline MGTMailboxResult mgt_mailbox_publish_terminal(
    MGTMailboxSlot *slot, uint32_t owned_state
) {
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    for (;;) {
        if ((control & MGT_MAILBOX_STATE_MASK) != owned_state) return MGT_MAILBOX_STALE;
        uint32_t terminal = MGT_MAILBOX_COMPLETE | (control & MGT_MAILBOX_LEASE_FLAGS);
        if (atomic_compare_exchange_weak_explicit(&slot->control, &control, terminal,
                memory_order_acq_rel, memory_order_acquire)) return MGT_MAILBOX_OK;
    }
}

static inline MGTMailboxResult mgt_mailbox_claim(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo,
    MGTMailboxRequest *request
) {
    MGTMailboxResult valid = mgt_mailbox_validate(slot, generation_hi, generation_lo);
    if (valid != MGT_MAILBOX_OK) return valid;
    if (request == NULL) return MGT_MAILBOX_INVALID;
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    MGTMailboxResult lease = mgt_mailbox_lease_result(control);
    if (lease != MGT_MAILBOX_OK) return lease;
    uint32_t state = control & MGT_MAILBOX_STATE_MASK;
    if (state != MGT_MAILBOX_POSTED)
        return state == MGT_MAILBOX_IDLE || state == MGT_MAILBOX_COMPLETE ? MGT_MAILBOX_EMPTY : MGT_MAILBOX_BUSY;
    uint32_t expected = MGT_MAILBOX_POSTED;
    if (!atomic_compare_exchange_strong_explicit(&slot->control, &expected,
            MGT_MAILBOX_EXECUTING, memory_order_acq_rel, memory_order_acquire)) {
        lease = mgt_mailbox_lease_result(expected);
        return lease == MGT_MAILBOX_OK ? MGT_MAILBOX_BUSY : lease;
    }
    /* Read mutable request fields only after owning the claim. Otherwise a
     * cancel/ack/new submission could replace them between load and CAS. */
    atomic_fetch_add_explicit(&slot->claimed_count, 1, memory_order_relaxed);
    if (slot->source_length > MGT_MAILBOX_SOURCE_CAPACITY || slot->sequence == 0
        || slot->sequence != atomic_load_explicit(&slot->highest_sequence, memory_order_acquire)) {
        slot->result_length = 0;
        slot->outcome = MGT_MAILBOX_ERROR;
        slot->status = 0;
        slot->execution_ns = 0;
        atomic_fetch_add_explicit(&slot->completed_count, 1, memory_order_relaxed);
        mgt_mailbox_publish_terminal(slot, MGT_MAILBOX_EXECUTING);
        return MGT_MAILBOX_INVALID;
    }
    request->sequence = slot->sequence;
    request->source = slot->source;
    request->length = slot->source_length;
    return MGT_MAILBOX_OK;
}

static inline MGTMailboxResult mgt_mailbox_complete(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo,
    uint64_t sequence, uint32_t outcome, int32_t status, const void *bytes,
    size_t length, uint64_t execution_ns
) {
    MGTMailboxResult valid = mgt_mailbox_validate(slot, generation_hi, generation_lo);
    if (valid != MGT_MAILBOX_OK) return valid;
    if (mgt_mailbox_state(slot) != MGT_MAILBOX_EXECUTING) return MGT_MAILBOX_BUSY;
    if (sequence != slot->sequence) return MGT_MAILBOX_STALE;
    MGTMailboxResult result = MGT_MAILBOX_OK;
    if (length > MGT_MAILBOX_RESULT_CAPACITY) result = MGT_MAILBOX_CAPACITY;
    else if ((bytes == NULL && length != 0) || outcome > MGT_MAILBOX_UNKNOWN)
        result = MGT_MAILBOX_INVALID;
    if (result != MGT_MAILBOX_OK) { outcome = MGT_MAILBOX_UNKNOWN; length = 0; }
    if (length != 0) memcpy(slot->result, bytes, length);
    slot->result_length = (uint32_t)length;
    slot->outcome = outcome;
    slot->status = status;
    slot->execution_ns = execution_ns;
    if (outcome == MGT_MAILBOX_UNKNOWN)
        atomic_fetch_or_explicit(&slot->control, MGT_MAILBOX_LEASE_FLAGS, memory_order_acq_rel);
    atomic_fetch_add_explicit(&slot->completed_count, 1, memory_order_relaxed);
    valid = mgt_mailbox_publish_terminal(slot, MGT_MAILBOX_EXECUTING);
    return valid == MGT_MAILBOX_OK ? result : valid;
}

/* A short buffer never marks a receipt read. The producer must copy all
 * result bytes and metadata before it can acknowledge/reuse the slot. */
static inline MGTMailboxResult mgt_mailbox_read(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo,
    uint64_t sequence, MGTMailboxReceipt *receipt, void *bytes, size_t capacity
) {
    MGTMailboxResult valid = mgt_mailbox_validate(slot, generation_hi, generation_lo);
    if (valid != MGT_MAILBOX_OK) return valid;
    if (receipt == NULL) return MGT_MAILBOX_INVALID;
    uint32_t state = mgt_mailbox_state(slot);
    if (state != MGT_MAILBOX_COMPLETE)
        return state == MGT_MAILBOX_IDLE ? MGT_MAILBOX_EMPTY : MGT_MAILBOX_BUSY;
    if (sequence != slot->sequence) return MGT_MAILBOX_STALE;
    if (slot->result_length > MGT_MAILBOX_RESULT_CAPACITY || slot->outcome > MGT_MAILBOX_UNKNOWN)
        return MGT_MAILBOX_INVALID;
    if (capacity < slot->result_length || (bytes == NULL && slot->result_length != 0))
        return MGT_MAILBOX_CAPACITY;
    MGTMailboxReceipt observed = {
        slot->generation_hi, slot->generation_lo, slot->sequence, slot->outcome,
        slot->status, slot->result_length, slot->execution_ns
    };
    if (slot->result_length != 0) memcpy(bytes, slot->result, slot->result_length);
    *receipt = observed;
    atomic_fetch_or_explicit(&slot->control, MGT_MAILBOX_READ_FLAG, memory_order_release);
    return MGT_MAILBOX_OK;
}

static inline MGTMailboxResult mgt_mailbox_ack(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo, uint64_t sequence
) {
    MGTMailboxResult valid = mgt_mailbox_validate(slot, generation_hi, generation_lo);
    if (valid != MGT_MAILBOX_OK) return valid;
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    if ((control & MGT_MAILBOX_STATE_MASK) != MGT_MAILBOX_COMPLETE) return MGT_MAILBOX_BUSY;
    if (sequence != slot->sequence) return MGT_MAILBOX_STALE;
    if (!(control & MGT_MAILBOX_READ_FLAG)) return MGT_MAILBOX_INVALID;
    for (;;) {
        if ((control & MGT_MAILBOX_STATE_MASK) != MGT_MAILBOX_COMPLETE
            || !(control & MGT_MAILBOX_READ_FLAG)) return MGT_MAILBOX_STALE;
        if (atomic_compare_exchange_weak_explicit(&slot->control, &control,
                MGT_MAILBOX_IDLE | (control & MGT_MAILBOX_LEASE_FLAGS),
                memory_order_acq_rel, memory_order_acquire)) return MGT_MAILBOX_OK;
    }
}

/* RESERVING is exclusively held either while the producer copies a new
 * request, or after cancellation wins against the consumer's POSTED CAS. */
static inline MGTMailboxResult mgt_mailbox_finish_cancel(MGTMailboxSlot *slot) {
    slot->result_length = 0;
    slot->outcome = MGT_MAILBOX_CANCELLED;
    slot->status = 0;
    slot->execution_ns = 0;
    atomic_fetch_add_explicit(&slot->completed_count, 1, memory_order_relaxed);
    return mgt_mailbox_publish_terminal(slot, MGT_MAILBOX_RESERVING);
}

static inline MGTMailboxResult mgt_mailbox_cancel(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo, uint64_t sequence
) {
    MGTMailboxResult valid = mgt_mailbox_validate(slot, generation_hi, generation_lo);
    if (valid != MGT_MAILBOX_OK) return valid;
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    MGTMailboxResult lease = mgt_mailbox_lease_result(control);
    if (lease != MGT_MAILBOX_OK) return lease;
    uint32_t state = control & MGT_MAILBOX_STATE_MASK;
    if (state == MGT_MAILBOX_IDLE) return MGT_MAILBOX_EMPTY;
    if (state == MGT_MAILBOX_RESERVING) return MGT_MAILBOX_BUSY;
    if (sequence != slot->sequence) return MGT_MAILBOX_STALE;
    if (state == MGT_MAILBOX_COMPLETE) return MGT_MAILBOX_DUPLICATE;
    if (state != MGT_MAILBOX_POSTED) return MGT_MAILBOX_BUSY;
    uint32_t expected = MGT_MAILBOX_POSTED;
    if (!atomic_compare_exchange_strong_explicit(&slot->control, &expected,
            MGT_MAILBOX_RESERVING, memory_order_acq_rel, memory_order_acquire)) {
        lease = mgt_mailbox_lease_result(expected);
        if (lease != MGT_MAILBOX_OK) return lease;
        return (expected & MGT_MAILBOX_STATE_MASK) == MGT_MAILBOX_COMPLETE
            ? MGT_MAILBOX_DUPLICATE : MGT_MAILBOX_BUSY;
    }
    return mgt_mailbox_finish_cancel(slot);
}

static inline MGTMailboxResult mgt_mailbox_invalidate(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo, uint32_t flags
) {
    MGTMailboxResult valid = mgt_mailbox_validate(slot, generation_hi, generation_lo);
    if (valid != MGT_MAILBOX_OK) return valid;
    /* The flag and POSTED claim share one atomic word: once this publishes,
     * no new consumer can win. An earlier EXECUTING owner keeps its receipt. */
    uint32_t control = atomic_fetch_or_explicit(&slot->control, flags, memory_order_acq_rel) | flags;
    while ((control & MGT_MAILBOX_STATE_MASK) == MGT_MAILBOX_POSTED) {
        uint32_t reserved = MGT_MAILBOX_RESERVING | (control & MGT_MAILBOX_LEASE_FLAGS);
        if (atomic_compare_exchange_strong_explicit(&slot->control, &control, reserved,
                memory_order_acq_rel, memory_order_acquire)) return mgt_mailbox_finish_cancel(slot);
    }
    return MGT_MAILBOX_OK;
}

static inline MGTMailboxResult mgt_mailbox_close(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo
) {
    return mgt_mailbox_invalidate(slot, generation_hi, generation_lo, MGT_MAILBOX_CLOSED_FLAG);
}

static inline MGTMailboxResult mgt_mailbox_poison(
    MGTMailboxSlot *slot, uint64_t generation_hi, uint64_t generation_lo
) {
    return mgt_mailbox_invalidate(slot, generation_hi, generation_lo, MGT_MAILBOX_LEASE_FLAGS);
}

static inline MGTMailboxResult mgt_mailbox_tick(MGTMailboxSlot *slot, uint64_t now_ns) {
    if (slot == NULL) return MGT_MAILBOX_INVALID;
    MGTMailboxResult valid = mgt_mailbox_validate(slot, slot->generation_hi, slot->generation_lo);
    if (valid != MGT_MAILBOX_OK) return valid;
    MGTMailboxResult lease = mgt_mailbox_lease_result(
        atomic_load_explicit(&slot->control, memory_order_acquire));
    if (lease != MGT_MAILBOX_OK) return lease;
    atomic_store_explicit(&slot->heartbeat_ns, now_ns, memory_order_relaxed);
    atomic_fetch_add_explicit(&slot->heartbeat_count, 1, memory_order_release);
    return MGT_MAILBOX_OK;
}

#endif
