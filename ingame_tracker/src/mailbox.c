#include "mailbox.h"

#include "sys.h"
#include "text.h"

#define MAILBOX_INITIALIZER                                                                                       \
  {                                                                                                               \
    .magic = { 'O', 'O', 'T', 'R', 'C', 'O', 'N', '1' }, .version = MAILBOX_VERSION,                              \
    .header_size = MAILBOX_HEADER_SIZE, .capacity = MAILBOX_CAPACITY, .entry_size = MAILBOX_ENTRY_SIZE,           \
    .module_version = MAILBOX_MODULE_VERSION,                                                                     \
  }

/* In the module's data, so its magic is in memory from the start; the client scans for it. */
static mailbox_t shared __attribute__((used, aligned(16))) = MAILBOX_INITIALIZER;

static const char not_running[] = "Archipelago client not running";
static const char not_connected[] = "Archipelago: not connected";
static const char connecting[] = "Archipelago: connecting to ";

mailbox_t *mailbox_shared(void)
{
  return &shared;
}

void mailbox_blank(mailbox_t *box)
{
  *box = (mailbox_t)MAILBOX_INITIALIZER;
}

void mailbox_set_seed(mailbox_t *box, const char *seed_id)
{
  text_copy(box->seed_id, sizeof(box->seed_id), seed_id);
}

void mailbox_start(mailbox_client_t *client, uint64_t now)
{
  client->heartbeat = __atomic_load_n(&mailbox_shared()->heartbeat, __ATOMIC_RELAXED);
  client->heartbeat_ms = now;
}

static console_kind_t kind_of(uint8_t kind)
{
  unsigned index = (unsigned)kind - MAILBOX_KIND_FIRST;
  return index < CONSOLE_KIND_COUNT ? (console_kind_t)index : CONSOLE_SERVER; /* a kind of a later client */
}

static bool hear_heartbeat(mailbox_t *box, mailbox_client_t *client, uint64_t now)
{
  uint32_t heartbeat = __atomic_load_n(&box->heartbeat, __ATOMIC_RELAXED);
  if (heartbeat == client->heartbeat)
    return false;
  client->heartbeat = heartbeat;
  client->heartbeat_ms = now;
  client->heard = true;
  return true;
}

/* the entries [from, head) copied out of the mailbox while it may be written */
static mailbox_entry_t taken[MAILBOX_CAPACITY];

bool mailbox_poll(mailbox_t *box, mailbox_client_t *client, console_log_t *log, uint64_t now)
{
  hear_heartbeat(box, client, now);
  uint32_t before = __atomic_load_n(&box->sequence, __ATOMIC_ACQUIRE);
  if ((before & 1) || before == client->sequence)
    return false;
  uint32_t head = __atomic_load_n(&box->head, __ATOMIC_RELAXED);
  uint32_t from = box->read_head;
  if (head < from) /* a client that started its count again: nothing of it is taken twice */
    from = head;
  if (head - from > MAILBOX_CAPACITY)
    from = head - MAILBOX_CAPACITY;
  uint8_t status = __atomic_load_n(&box->status, __ATOMIC_RELAXED);
  char status_text[MAILBOX_STATUS_ROOM];
  memcpy(status_text, box->status_text, sizeof(status_text));
  for (uint32_t n = from; n != head; n++)
    memcpy(&taken[n - from], &box->entries[n % MAILBOX_CAPACITY], sizeof(taken[0]));
  __atomic_thread_fence(__ATOMIC_ACQUIRE);
  if (__atomic_load_n(&box->sequence, __ATOMIC_RELAXED) != before)
    return false; /* written meanwhile: the next frame reads it whole */
  for (uint32_t n = from; n != head; n++) {
    const mailbox_entry_t *entry = &taken[n - from];
    size_t length = entry->length < MAILBOX_TEXT_ROOM ? entry->length : MAILBOX_TEXT_ROOM;
    if (entry->kind)
      consolelog_add(log, kind_of(entry->kind), (const uint8_t *)entry->text, length, now);
  }
  status_text[MAILBOX_STATUS_ROOM - 1] = 0;
  bool changed = head != from || status != client->status || !text_equal(status_text, client->status_text);
  client->sequence = before;
  client->status = status;
  memcpy(client->status_text, status_text, sizeof(status_text));
  box->read_head = head;
  return changed;
}

void mailbox_status_line(const mailbox_client_t *client, bool archipelago, uint64_t now, char *out, size_t room)
{
  if (!room)
    return;
  out[0] = 0;
  bool silent = now >= client->heartbeat_ms && now - client->heartbeat_ms >= MAILBOX_SILENT_MS;
  if (silent) {
    if (archipelago || client->heard)
      text_copy(out, room, not_running);
    return;
  }
  if (!client->heard || client->status == MAILBOX_STATUS_CONNECTED || client->status == MAILBOX_STATUS_NONE)
    return;
  if (client->status == MAILBOX_STATUS_DISCONNECTED) {
    text_copy(out, room, not_connected);
    return;
  }
  size_t at = text_copy(out, room, connecting);
  console_sanitize(out + at, room - at, (const uint8_t *)client->status_text, strlen(client->status_text));
}
