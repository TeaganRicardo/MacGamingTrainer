#define _POSIX_C_SOURCE 200809L
#if defined(__APPLE__)
/* Darwin hides O_NOFOLLOW without the native feature namespace. */
#define _DARWIN_C_SOURCE 1
#endif

/* The producer is the shipped CommandMailbox.c ABI. This fixture replaces
 * only the game's Lua consumer, using the same native protocol in a process
 * with its own mapping. No Python code reads or writes atomic slot fields. */
#include <errno.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "MailboxProtocol.h"

typedef struct {
    uint32_t state;
    uint32_t flags;
    uint64_t highest_sequence;
    uint64_t claimed_count;
    uint64_t completed_count;
} MGTTestMailboxSnapshot;

void *MGTTestMailboxMap(const char *path, uint64_t generation_hi, uint64_t generation_lo) {
    int descriptor = open(path, O_RDWR | O_NOFOLLOW);
    if (descriptor < 0) return NULL;
    struct stat metadata;
    if (fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode)
        || metadata.st_size != (off_t)sizeof(MGTMailboxSlot)) {
        close(descriptor);
        errno = EINVAL;
        return NULL;
    }
    MGTMailboxSlot *slot = mmap(NULL, sizeof(*slot), PROT_READ | PROT_WRITE,
                               MAP_SHARED, descriptor, 0);
    close(descriptor);
    if (slot == MAP_FAILED) return NULL;
    if (mgt_mailbox_validate(slot, generation_hi, generation_lo) != MGT_MAILBOX_OK) {
        munmap(slot, sizeof(*slot));
        errno = EINVAL;
        return NULL;
    }
    return slot;
}

int MGTTestMailboxUnmap(MGTMailboxSlot *slot) {
    return munmap(slot, sizeof(*slot));
}

int MGTTestMailboxClaim(MGTMailboxSlot *slot, MGTMailboxRequest *request) {
    return mgt_mailbox_claim(slot, slot->generation_hi, slot->generation_lo, request);
}

int MGTTestMailboxComplete(MGTMailboxSlot *slot, uint64_t sequence, uint32_t outcome,
                           int32_t status, const void *bytes, size_t length,
                           uint64_t execution_ns) {
    return mgt_mailbox_complete(slot, slot->generation_hi, slot->generation_lo,
                                sequence, outcome, status, bytes, length, execution_ns);
}

void MGTTestMailboxInspect(MGTMailboxSlot *slot, MGTTestMailboxSnapshot *snapshot) {
    uint32_t control = atomic_load_explicit(&slot->control, memory_order_acquire);
    snapshot->state = control & MGT_MAILBOX_STATE_MASK;
    snapshot->flags = control & MGT_MAILBOX_LEASE_FLAGS;
    snapshot->highest_sequence = atomic_load_explicit(&slot->highest_sequence, memory_order_acquire);
    snapshot->claimed_count = atomic_load_explicit(&slot->claimed_count, memory_order_acquire);
    snapshot->completed_count = atomic_load_explicit(&slot->completed_count, memory_order_acquire);
}
