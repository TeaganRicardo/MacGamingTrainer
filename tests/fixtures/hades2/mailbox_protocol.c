#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "MailboxProtocol.h"

static const uint64_t generation_hi = UINT64_C(0x1122334455667788);
static const uint64_t generation_lo = UINT64_C(0x99aabbccddeeff00);

static uint64_t monotonic_ns(void) {
    struct timespec now;
    assert(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}

static void briefly_wait(void) {
    struct timespec delay = {0, 1000000};
    nanosleep(&delay, NULL);
}

static void send_bytes(int descriptor, const void *data, size_t length) {
    const unsigned char *bytes = data;
    while (length != 0) {
        ssize_t sent = write(descriptor, bytes, length);
        if (sent < 0 && errno == EINTR) continue;
        assert(sent > 0);
        bytes += sent;
        length -= (size_t)sent;
    }
}

static void receive_bytes(int descriptor, void *data, size_t length) {
    unsigned char *bytes = data;
    while (length != 0) {
        ssize_t received = read(descriptor, bytes, length);
        if (received < 0 && errno == EINTR) continue;
        assert(received > 0);
        bytes += received;
        length -= (size_t)received;
    }
}

static MGTMailboxSlot *shared_slot(int descriptor) {
    void *mapping = mmap(NULL, sizeof(MGTMailboxSlot), PROT_READ | PROT_WRITE,
                         MAP_SHARED, descriptor, 0);
    assert(mapping != MAP_FAILED);
    return mapping;
}

static MGTMailboxSlot *local_slot(void) {
    MGTMailboxSlot *slot = calloc(1, sizeof(*slot));
    assert(slot != NULL);
    assert(mgt_mailbox_init(slot, generation_hi, generation_lo,
        (uint32_t)getpid(), (uint32_t)getpid()) == MGT_MAILBOX_OK);
    return slot;
}

static void validation_and_receipts(void) {
    MGTMailboxSlot *slot = local_slot();
    assert(mgt_mailbox_init(slot, generation_hi + 1, generation_lo,
        (uint32_t)getpid(), (uint32_t)getpid()) == MGT_MAILBOX_INVALID);
    assert(mgt_mailbox_validate(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 0, "x", 1) == MGT_MAILBOX_INVALID);
    assert(mgt_mailbox_submit(slot, generation_hi + 1, generation_lo, 1, "x", 1) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, NULL, 1) == MGT_MAILBOX_INVALID);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "x",
        (size_t)MGT_MAILBOX_SOURCE_CAPACITY + 1) == MGT_MAILBOX_CAPACITY);
    assert(mgt_mailbox_state(slot) == MGT_MAILBOX_IDLE);
    assert(atomic_load(&slot->highest_sequence) == 0);
    const unsigned char source[] = {'a', 0, 'b'};
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, source, sizeof(source)) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, source, sizeof(source)) == MGT_MAILBOX_DUPLICATE);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, "axb", 3) == MGT_MAILBOX_INVALID);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 3, "x", 1) == MGT_MAILBOX_BUSY);
    MGTMailboxRequest request;
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_BUSY);
    assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, 1,
        MGT_MAILBOX_SUCCESS, 0, source, sizeof(source), 99) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_state(slot) == MGT_MAILBOX_EXECUTING);
    assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, 2,
        MGT_MAILBOX_ERROR, -77, source, sizeof(source), 99) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 2) == MGT_MAILBOX_INVALID);
    MGTMailboxReceipt receipt;
    unsigned char result[3] = {0};
    assert(mgt_mailbox_read(slot, generation_hi, generation_lo, 2,
        &receipt, result, 2) == MGT_MAILBOX_CAPACITY);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 2) == MGT_MAILBOX_INVALID);
    assert(mgt_mailbox_read(slot, generation_hi, generation_lo, 2,
        NULL, result, sizeof(result)) == MGT_MAILBOX_INVALID);
    assert(mgt_mailbox_read(slot, generation_hi, generation_lo, 1,
        &receipt, result, sizeof(result)) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_read(slot, generation_hi, generation_lo, 2,
        &receipt, result, sizeof(result)) == MGT_MAILBOX_OK);
    assert(memcmp(result, source, sizeof(source)) == 0);
    assert(receipt.length == 3 && receipt.outcome == MGT_MAILBOX_ERROR);
    assert(receipt.status == -77 && receipt.execution_ns == 99);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, source, sizeof(source)) == MGT_MAILBOX_DUPLICATE);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 2) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, source, sizeof(source)) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "x", 1) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, UINT64_MAX, "x", 1) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, UINT64_MAX,
        MGT_MAILBOX_SUCCESS, 0, NULL, 0, 0) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_read(slot, generation_hi, generation_lo, UINT64_MAX,
        &receipt, NULL, 0) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, UINT64_MAX) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "x", 1) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 0, "x", 1) == MGT_MAILBOX_INVALID);
    assert(atomic_load(&slot->claimed_count) == 2);
    assert(atomic_load(&slot->completed_count) == 2);
    free(slot);
}

static MGTMailboxReceipt read_receipt(MGTMailboxSlot *slot, uint64_t sequence) {
    MGTMailboxReceipt receipt;
    unsigned char result[MGT_MAILBOX_RESULT_CAPACITY];
    assert(mgt_mailbox_read(slot, generation_hi, generation_lo, sequence,
        &receipt, result, sizeof(result)) == MGT_MAILBOX_OK);
    return receipt;
}

static void cancellation_and_close(void) {
    MGTMailboxSlot *slot = local_slot();
    MGTMailboxRequest request;
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "first", 5) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_cancel(slot, generation_hi, generation_lo, 2) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_cancel(slot, generation_hi, generation_lo, 1) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_EMPTY);
    assert(read_receipt(slot, 1).outcome == MGT_MAILBOX_CANCELLED);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 1) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "first", 5) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, "next", 4) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_close(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_CLOSED);
    assert(read_receipt(slot, 2).outcome == MGT_MAILBOX_CANCELLED);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 2) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_close(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 3, "later", 5) == MGT_MAILBOX_CLOSED);
    assert(mgt_mailbox_init(slot, generation_hi, generation_lo,
        (uint32_t)getpid(), (uint32_t)getpid()) == MGT_MAILBOX_INVALID);
    assert(atomic_load(&slot->claimed_count) == 0);
    free(slot);

    slot = local_slot();
    assert(mgt_mailbox_tick(slot, 1500) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "active", 6) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_cancel(slot, generation_hi, generation_lo, 1) == MGT_MAILBOX_BUSY);
    assert(mgt_mailbox_close(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_state(slot) == MGT_MAILBOX_EXECUTING);
    assert(request.length == 6 && memcmp(request.source, "active", 6) == 0);
    assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, 1,
        MGT_MAILBOX_SUCCESS, 42, "final", 5, 88) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_close(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    MGTMailboxReceipt receipt = read_receipt(slot, 1);
    assert(receipt.outcome == MGT_MAILBOX_SUCCESS && receipt.status == 42);
    assert(receipt.length == 5 && receipt.execution_ns == 88);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 1) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_tick(slot, 2000) == MGT_MAILBOX_CLOSED);
    assert(atomic_load(&slot->heartbeat_count) == 1 && atomic_load(&slot->heartbeat_ns) == 1500);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, "later", 5) == MGT_MAILBOX_CLOSED);
    free(slot);
}

static void unknown_is_permanent(void) {
    MGTMailboxSlot *slot = local_slot();
    MGTMailboxRequest request;
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "active", 6) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_poison(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_state(slot) == MGT_MAILBOX_EXECUTING);
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_POISONED);
    assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, 1,
        MGT_MAILBOX_SUCCESS, 0, "late", 4, 200) == MGT_MAILBOX_OK);
    assert(read_receipt(slot, 1).outcome == MGT_MAILBOX_SUCCESS);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 1) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_close(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_flags(slot) == MGT_MAILBOX_LEASE_FLAGS);
    assert(mgt_mailbox_tick(slot, 9000) == MGT_MAILBOX_POISONED);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, "later", 5) == MGT_MAILBOX_POISONED);
    assert(mgt_mailbox_init(slot, generation_hi + 1, generation_lo,
        (uint32_t)getpid(), (uint32_t)getpid()) == MGT_MAILBOX_INVALID);
    free(slot);

    for (unsigned mode = 0; mode < 3; ++mode) {
        slot = local_slot();
        assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "once", 4) == MGT_MAILBOX_OK);
        assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_OK);
        MGTMailboxResult completed;
        if (mode == 0) {
            completed = mgt_mailbox_complete(slot, generation_hi, generation_lo, 1,
                MGT_MAILBOX_UNKNOWN, 2, "native failure", 14, 300);
            assert(completed == MGT_MAILBOX_OK);
        } else if (mode == 1) {
            completed = mgt_mailbox_complete(slot, generation_hi, generation_lo, 1,
                MGT_MAILBOX_SUCCESS, 0, "x", (size_t)MGT_MAILBOX_RESULT_CAPACITY + 1, 300);
            assert(completed == MGT_MAILBOX_CAPACITY);
        } else {
            completed = mgt_mailbox_complete(slot, generation_hi, generation_lo, 1,
                MGT_MAILBOX_SUCCESS, 0, NULL, 1, 300);
            assert(completed == MGT_MAILBOX_INVALID);
        }
        assert(read_receipt(slot, 1).outcome == MGT_MAILBOX_UNKNOWN);
        assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 1) == MGT_MAILBOX_OK);
        assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, "later", 5) == MGT_MAILBOX_POISONED);
        free(slot);
    }

    slot = local_slot();
    assert(mgt_mailbox_poison(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "new", 3) == MGT_MAILBOX_POISONED);
    free(slot);
}

static void malformed_shared_fields(void) {
    MGTMailboxSlot *slot = local_slot();
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "x", 1) == MGT_MAILBOX_OK);
    /* Deliberate wire corruption models an invalid peer/ABI. No native work
     * receives a request view, and the rejection still has a full receipt. */
    slot->source_length = MGT_MAILBOX_SOURCE_CAPACITY + 1;
    MGTMailboxRequest request = {999, NULL, 0};
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_INVALID);
    assert(request.sequence == 999 && request.source == NULL);
    assert(read_receipt(slot, 1).outcome == MGT_MAILBOX_ERROR);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 1) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 2, "next", 4) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_claim(slot, generation_hi, generation_lo, &request) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_complete(slot, generation_hi, generation_lo + 1, 2,
        MGT_MAILBOX_SUCCESS, 0, "ok", 2, 5) == MGT_MAILBOX_STALE);
    assert(mgt_mailbox_state(slot) == MGT_MAILBOX_EXECUTING);
    assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, 2,
        MGT_MAILBOX_SUCCESS, 0, "ok", 2, 5) == MGT_MAILBOX_OK);
    slot->result_length = MGT_MAILBOX_RESULT_CAPACITY + 1;
    MGTMailboxReceipt receipt;
    char result[4];
    assert(mgt_mailbox_read(slot, generation_hi, generation_lo, 2,
        &receipt, result, sizeof(result)) == MGT_MAILBOX_INVALID);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 2) == MGT_MAILBOX_INVALID);
    assert(mgt_mailbox_poison(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 3, "next", 4) == MGT_MAILBOX_POISONED);
    free(slot);
}

static void cancel_execute_race(void) {
    enum { iterations = 1024 };
    FILE *backing = tmpfile();
    assert(backing != NULL);
    int descriptor = fileno(backing);
    assert(ftruncate(descriptor, (off_t)sizeof(MGTMailboxSlot)) == 0);
    MGTMailboxSlot *slot = shared_slot(descriptor);
    int parent_to_child[2], child_to_parent[2];
    assert(pipe(parent_to_child) == 0 && pipe(child_to_parent) == 0);
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        close(parent_to_child[1]);
        close(child_to_parent[0]);
        assert(munmap(slot, sizeof(*slot)) == 0);
        slot = shared_slot(descriptor);
        for (uint64_t sequence = 1; sequence <= iterations; ++sequence) {
            unsigned char mode;
            receive_bytes(parent_to_child[0], &mode, 1);
            MGTMailboxRequest request;
            MGTMailboxResult claimed = mgt_mailbox_claim(slot, generation_hi, generation_lo, &request);
            uint32_t executed = 0;
            if (claimed == MGT_MAILBOX_OK) {
                assert(request.sequence == sequence && request.length == sizeof(uint64_t));
                if (mode == 'e') {
                    send_bytes(child_to_parent[1], "c", 1);
                    receive_bytes(parent_to_child[0], &mode, 1);
                    assert(mode == 'f');
                }
                uint64_t input;
                memcpy(&input, request.source, sizeof(input));
                assert(input == sequence * 13);
                uint64_t result = input + 1;
                executed = 1;
                assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, sequence,
                    MGT_MAILBOX_SUCCESS, 0, &result, sizeof(result), 1) == MGT_MAILBOX_OK);
            } else {
                assert(claimed == MGT_MAILBOX_EMPTY || claimed == MGT_MAILBOX_BUSY);
            }
            send_bytes(child_to_parent[1], &executed, sizeof(executed));
        }
        assert(munmap(slot, sizeof(*slot)) == 0);
        fclose(backing);
        close(parent_to_child[0]);
        close(child_to_parent[1]);
        _exit(0);
    }
    close(parent_to_child[0]);
    close(child_to_parent[1]);
    assert(mgt_mailbox_init(slot, generation_hi, generation_lo,
        (uint32_t)getpid(), (uint32_t)child) == MGT_MAILBOX_OK);
    unsigned cancellations = 0, executions = 0;
    for (uint64_t sequence = 1; sequence <= iterations; ++sequence) {
        uint64_t input = sequence * 13;
        assert(mgt_mailbox_submit(slot, generation_hi, generation_lo,
            sequence, &input, sizeof(input)) == MGT_MAILBOX_OK);
        MGTMailboxResult cancelled;
        if (sequence % 4 == 0) {
            cancelled = mgt_mailbox_cancel(slot, generation_hi, generation_lo, sequence);
            assert(cancelled == MGT_MAILBOX_OK);
            send_bytes(parent_to_child[1], "c", 1);
        } else if (sequence % 4 == 1) {
            send_bytes(parent_to_child[1], "e", 1);
            unsigned char claimed;
            receive_bytes(child_to_parent[0], &claimed, 1);
            assert(claimed == 'c');
            cancelled = mgt_mailbox_cancel(slot, generation_hi, generation_lo, sequence);
            assert(cancelled == MGT_MAILBOX_BUSY);
            send_bytes(parent_to_child[1], "f", 1);
        } else {
            send_bytes(parent_to_child[1], "r", 1);
            if (sequence % 4 == 3) sched_yield();
            cancelled = mgt_mailbox_cancel(slot, generation_hi, generation_lo, sequence);
        }
        uint32_t executed;
        receive_bytes(child_to_parent[0], &executed, sizeof(executed));
        uint64_t result = 0;
        MGTMailboxReceipt receipt;
        assert(mgt_mailbox_read(slot, generation_hi, generation_lo, sequence,
            &receipt, &result, sizeof(result)) == MGT_MAILBOX_OK);
        if (cancelled == MGT_MAILBOX_OK) {
            assert(executed == 0 && receipt.outcome == MGT_MAILBOX_CANCELLED && receipt.length == 0);
            cancellations += 1;
        } else {
            assert(cancelled == MGT_MAILBOX_BUSY || cancelled == MGT_MAILBOX_DUPLICATE);
            assert(executed == 1 && receipt.outcome == MGT_MAILBOX_SUCCESS);
            assert(receipt.length == sizeof(result) && result == input + 1);
            executions += 1;
        }
        assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, sequence) == MGT_MAILBOX_OK);
        assert(mgt_mailbox_submit(slot, generation_hi, generation_lo,
            sequence, &input, sizeof(input)) == MGT_MAILBOX_STALE);
    }
    assert(cancellations != 0 && executions != 0 && cancellations + executions == iterations);
    assert(atomic_load(&slot->claimed_count) == executions);
    assert(atomic_load(&slot->completed_count) == iterations);
    int status;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    close(parent_to_child[1]);
    close(child_to_parent[0]);
    assert(munmap(slot, sizeof(*slot)) == 0);
    fclose(backing);
}

static void independent_mapping_lifetime(int consume_before_close) {
    FILE *backing = tmpfile();
    assert(backing != NULL);
    int descriptor = fileno(backing);
    assert(ftruncate(descriptor, (off_t)sizeof(MGTMailboxSlot)) == 0);
    MGTMailboxSlot *slot = shared_slot(descriptor);
    int parent_to_child[2], child_to_parent[2];
    assert(pipe(parent_to_child) == 0 && pipe(child_to_parent) == 0);
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        close(parent_to_child[1]);
        close(child_to_parent[0]);
        assert(munmap(slot, sizeof(*slot)) == 0);
        slot = shared_slot(descriptor);
        unsigned char signal;
        receive_bytes(parent_to_child[0], &signal, 1);
        MGTMailboxRequest request;
        MGTMailboxResult claimed = mgt_mailbox_claim(slot, generation_hi, generation_lo, &request);
        if (consume_before_close) {
            assert(claimed == MGT_MAILBOX_OK);
            send_bytes(child_to_parent[1], "c", 1);
            receive_bytes(parent_to_child[0], &signal, 1);
            assert(request.length == 6 && memcmp(request.source, "native", 6) == 0);
            assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, 1,
                MGT_MAILBOX_SUCCESS, 11, "retained", 8, 12) == MGT_MAILBOX_OK);
        } else assert(claimed == MGT_MAILBOX_CLOSED);
        MGTMailboxReceipt receipt = read_receipt(slot, 1);
        assert(mgt_mailbox_flags(slot) == MGT_MAILBOX_CLOSED_FLAG);
        assert(mgt_mailbox_state(slot) == MGT_MAILBOX_COMPLETE);
        send_bytes(child_to_parent[1], &receipt, sizeof(receipt));
        assert(munmap(slot, sizeof(*slot)) == 0);
        fclose(backing);
        close(parent_to_child[0]);
        close(child_to_parent[1]);
        _exit(0);
    }
    close(parent_to_child[0]);
    close(child_to_parent[1]);
    assert(mgt_mailbox_init(slot, generation_hi, generation_lo,
        (uint32_t)getpid(), (uint32_t)child) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1, "native", 6) == MGT_MAILBOX_OK);
    if (consume_before_close) {
        send_bytes(parent_to_child[1], "s", 1);
        unsigned char claimed;
        receive_bytes(child_to_parent[0], &claimed, 1);
        assert(claimed == 'c');
    }
    assert(mgt_mailbox_close(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
    assert(munmap(slot, sizeof(*slot)) == 0);
    fclose(backing);
    send_bytes(parent_to_child[1], "f", 1);
    MGTMailboxReceipt receipt;
    receive_bytes(child_to_parent[0], &receipt, sizeof(receipt));
    if (consume_before_close) {
        assert(receipt.outcome == MGT_MAILBOX_SUCCESS && receipt.status == 11);
        assert(receipt.length == 8 && receipt.execution_ns == 12);
    } else assert(receipt.outcome == MGT_MAILBOX_CANCELLED && receipt.length == 0);
    int status;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    close(parent_to_child[1]);
    close(child_to_parent[0]);
}

/* Only the initial ready signal uses a pipe. Every later request/reply and
 * slot reuse is published through the production acquire/release protocol. */
static void shared_publication_stream(void) {
    enum { iterations = 192 };
    FILE *backing = tmpfile();
    assert(backing != NULL);
    int descriptor = fileno(backing);
    assert(ftruncate(descriptor, (off_t)sizeof(MGTMailboxSlot)) == 0);
    MGTMailboxSlot *slot = shared_slot(descriptor);
    int ready[2];
    assert(pipe(ready) == 0);
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        close(ready[1]);
        assert(munmap(slot, sizeof(*slot)) == 0);
        slot = shared_slot(descriptor);
        unsigned char signal;
        receive_bytes(ready[0], &signal, 1);
        unsigned char *result = malloc(MGT_MAILBOX_RESULT_CAPACITY);
        assert(result != NULL);
        for (uint64_t sequence = 1; sequence <= iterations; ++sequence) {
            MGTMailboxRequest request;
            uint64_t deadline = monotonic_ns() + UINT64_C(5000000000);
            MGTMailboxResult claimed;
            while ((claimed = mgt_mailbox_claim(slot, generation_hi, generation_lo, &request))
                   != MGT_MAILBOX_OK) {
                assert(claimed == MGT_MAILBOX_EMPTY || claimed == MGT_MAILBOX_BUSY);
                assert(monotonic_ns() < deadline);
                briefly_wait();
            }
            assert(request.sequence == sequence);
            size_t source_length = sequence == 1 || sequence == iterations
                ? MGT_MAILBOX_SOURCE_CAPACITY : (size_t)sequence * 19;
            assert(request.length == source_length);
            unsigned char expected = (unsigned char)sequence;
            for (size_t index = 0; index < request.length; ++index)
                assert(request.source[index] == expected);
            size_t result_length = sequence == 1 || sequence == iterations
                ? MGT_MAILBOX_RESULT_CAPACITY : (size_t)sequence * 7;
            memset(result, (unsigned char)(expected ^ 0xa5u), result_length);
            assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, sequence,
                MGT_MAILBOX_SUCCESS, 17, result, result_length, sequence) == MGT_MAILBOX_OK);
        }
        free(result);
        assert(munmap(slot, sizeof(*slot)) == 0);
        fclose(backing);
        close(ready[0]);
        _exit(0);
    }
    close(ready[0]);
    assert(mgt_mailbox_init(slot, generation_hi, generation_lo,
        (uint32_t)getpid(), (uint32_t)child) == MGT_MAILBOX_OK);
    send_bytes(ready[1], "s", 1);
    close(ready[1]);
    unsigned char *source = malloc(MGT_MAILBOX_SOURCE_CAPACITY);
    unsigned char *result = malloc(MGT_MAILBOX_RESULT_CAPACITY);
    assert(source != NULL && result != NULL);
    for (uint64_t sequence = 1; sequence <= iterations; ++sequence) {
        size_t source_length = sequence == 1 || sequence == iterations
            ? MGT_MAILBOX_SOURCE_CAPACITY : (size_t)sequence * 19;
        memset(source, (unsigned char)sequence, source_length);
        assert(mgt_mailbox_submit(slot, generation_hi, generation_lo,
            sequence, source, source_length) == MGT_MAILBOX_OK);
        MGTMailboxReceipt receipt;
        uint64_t deadline = monotonic_ns() + UINT64_C(5000000000);
        MGTMailboxResult read;
        while ((read = mgt_mailbox_read(slot, generation_hi, generation_lo, sequence,
                  &receipt, result, MGT_MAILBOX_RESULT_CAPACITY)) != MGT_MAILBOX_OK) {
            assert(read == MGT_MAILBOX_EMPTY || read == MGT_MAILBOX_BUSY);
            assert(monotonic_ns() < deadline);
            briefly_wait();
        }
        size_t result_length = sequence == 1 || sequence == iterations
            ? MGT_MAILBOX_RESULT_CAPACITY : (size_t)sequence * 7;
        assert(receipt.length == result_length && receipt.status == 17 && receipt.execution_ns == sequence);
        unsigned char expected = (unsigned char)((unsigned char)sequence ^ 0xa5u);
        for (size_t index = 0; index < receipt.length; ++index) assert(result[index] == expected);
        assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, sequence) == MGT_MAILBOX_OK);
    }
    int status;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    free(source);
    free(result);
    assert(munmap(slot, sizeof(*slot)) == 0);
    fclose(backing);
}

static void roundtrip(void) {
    FILE *backing = tmpfile();
    assert(backing != NULL);
    int descriptor = fileno(backing);
    assert(ftruncate(descriptor, (off_t)sizeof(MGTMailboxSlot)) == 0);
    MGTMailboxSlot *slot = shared_slot(descriptor);
    int ready[2];
    assert(pipe(ready) == 0);
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        close(ready[1]);
        assert(munmap(slot, sizeof(*slot)) == 0);
        slot = shared_slot(descriptor);
        unsigned char signal;
        assert(read(ready[0], &signal, 1) == 1);
        assert(mgt_mailbox_validate(slot, generation_hi, generation_lo) == MGT_MAILBOX_OK);
        MGTMailboxRequest request;
        uint64_t deadline = monotonic_ns() + UINT64_C(5000000000);
        MGTMailboxResult result;
        while ((result = mgt_mailbox_claim(slot, generation_hi, generation_lo, &request))
               != MGT_MAILBOX_OK) {
            assert(result == MGT_MAILBOX_EMPTY || result == MGT_MAILBOX_BUSY);
            assert(monotonic_ns() < deadline);
            briefly_wait();
        }
        assert(request.sequence == 1);
        assert(request.length == strlen("return 'mailbox'"));
        assert(memcmp(request.source, "return 'mailbox'", request.length) == 0);
        const char response[] = "{\"ok\":true}";
        assert(mgt_mailbox_complete(slot, generation_hi, generation_lo, request.sequence,
            MGT_MAILBOX_SUCCESS, 0, response, sizeof(response) - 1, 1234) == MGT_MAILBOX_OK);
        assert(munmap(slot, sizeof(*slot)) == 0);
        fclose(backing);
        close(ready[0]);
        _exit(0);
    }
    close(ready[0]);
    assert(mgt_mailbox_init(slot, generation_hi, generation_lo,
        (uint32_t)getpid(), (uint32_t)child) == MGT_MAILBOX_OK);
    assert(mgt_mailbox_submit(slot, generation_hi, generation_lo, 1,
        "return 'mailbox'", strlen("return 'mailbox'")) == MGT_MAILBOX_OK);
    assert(write(ready[1], "x", 1) == 1);
    close(ready[1]);
    MGTMailboxReceipt receipt;
    char response[64];
    uint64_t deadline = monotonic_ns() + UINT64_C(5000000000);
    MGTMailboxResult result;
    while ((result = mgt_mailbox_read(slot, generation_hi, generation_lo, 1,
             &receipt, response, sizeof(response))) != MGT_MAILBOX_OK) {
        assert(result == MGT_MAILBOX_EMPTY || result == MGT_MAILBOX_BUSY);
        assert(monotonic_ns() < deadline);
        briefly_wait();
    }
    assert(receipt.generation_hi == generation_hi && receipt.generation_lo == generation_lo);
    assert(receipt.sequence == 1 && receipt.outcome == MGT_MAILBOX_SUCCESS);
    assert(receipt.status == 0 && receipt.execution_ns == 1234);
    assert(receipt.length == strlen("{\"ok\":true}"));
    assert(memcmp(response, "{\"ok\":true}", receipt.length) == 0);
    assert(mgt_mailbox_ack(slot, generation_hi, generation_lo, 1) == MGT_MAILBOX_OK);
    int status;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    assert(munmap(slot, sizeof(*slot)) == 0);
    fclose(backing);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    if (strcmp(argv[1], "roundtrip") == 0) roundtrip();
    else if (strcmp(argv[1], "validation_and_receipts") == 0) validation_and_receipts();
    else if (strcmp(argv[1], "cancellation_and_close") == 0) cancellation_and_close();
    else if (strcmp(argv[1], "unknown_is_permanent") == 0) unknown_is_permanent();
    else if (strcmp(argv[1], "malformed_shared_fields") == 0) malformed_shared_fields();
    else if (strcmp(argv[1], "cancel_execute_race") == 0) cancel_execute_race();
    else if (strcmp(argv[1], "independent_mapping_lifetime") == 0) {
        independent_mapping_lifetime(0);
        independent_mapping_lifetime(1);
    }
    else if (strcmp(argv[1], "shared_publication_stream") == 0) shared_publication_stream();
    else assert(!"unknown mailbox fixture case");
    return 0;
}
