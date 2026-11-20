/* The Archipelago console's mailbox: a block of this module's own memory that the randomizer's desktop client (the
 * Archipelago client, src/oot_rando/archipelago/console_bridge.py) finds by its magic and writes, since the game has
 * no network of its own. The client writes lines, its status and a heartbeat; the module reads them each frame and
 * writes back the seed it runs and how far it has read. The layout is in docs/ingame-tracker-format.md
 * ("The console's mailbox"); the offsets below are checked against the struct. */
#ifndef MAILBOX_H
#define MAILBOX_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "consolelog.h"

#define MAILBOX_VERSION       1
#define MAILBOX_HEADER_SIZE   0x80
#define MAILBOX_CAPACITY      32
#define MAILBOX_ENTRY_SIZE    168
#define MAILBOX_TEXT_ROOM     164 /* an entry's UTF-8 text: `length` bytes of it count */
#define MAILBOX_STATUS_ROOM   64
#define MAILBOX_SEED_ID_ROOM  24
#define MAILBOX_MODULE_VERSION 0x000700 /* 0.7.0: major << 16 | minor << 8 | patch */

/* the client's status */
enum { MAILBOX_STATUS_NONE, MAILBOX_STATUS_DISCONNECTED, MAILBOX_STATUS_CONNECTING, MAILBOX_STATUS_CONNECTED };
/* an entry's kind: console_kind_t + 1 (0: empty) */
enum { MAILBOX_KIND_FIRST = 1 };

typedef struct {
  uint8_t kind, length;
  uint16_t reserved;
  char text[MAILBOX_TEXT_ROOM];
} mailbox_entry_t;

typedef struct {
  char magic[8];                       /* "OOTRCON1" */
  uint16_t version, header_size, capacity, entry_size;
  uint32_t sequence;                   /* client: odd while it writes entries, head and status, even after */
  uint32_t head;                       /* client: entries ever written; entry n is at n % capacity */
  uint32_t heartbeat;                  /* client: counts up about once a second while it runs */
  uint8_t status;                      /* client: MAILBOX_STATUS_* */
  uint8_t reserved[3];
  char status_text[MAILBOX_STATUS_ROOM]; /* client: the server, "as" the slot (UTF-8, NUL-terminated) */
  char seed_id[MAILBOX_SEED_ID_ROOM];  /* module: the seed file's id, once it is read */
  uint32_t read_head;                  /* module: entries it has taken */
  uint32_t module_version;             /* module: MAILBOX_MODULE_VERSION */
  mailbox_entry_t entries[MAILBOX_CAPACITY];
} mailbox_t;

_Static_assert(offsetof(mailbox_t, sequence) == 0x10 && offsetof(mailbox_t, head) == 0x14, "mailbox layout");
_Static_assert(offsetof(mailbox_t, heartbeat) == 0x18 && offsetof(mailbox_t, status) == 0x1C, "mailbox layout");
_Static_assert(offsetof(mailbox_t, status_text) == 0x20 && offsetof(mailbox_t, seed_id) == 0x60, "mailbox layout");
_Static_assert(offsetof(mailbox_t, read_head) == 0x78 && offsetof(mailbox_t, module_version) == 0x7C, "mailbox layout");
_Static_assert(offsetof(mailbox_t, entries) == MAILBOX_HEADER_SIZE, "mailbox layout");
_Static_assert(sizeof(mailbox_entry_t) == MAILBOX_ENTRY_SIZE, "mailbox layout");
_Static_assert(offsetof(mailbox_entry_t, text) == 4, "mailbox layout");

/* What the module knows of the client. */
typedef struct {
  uint32_t sequence;     /* the last one read whole */
  uint32_t heartbeat;
  uint64_t heartbeat_ms; /* when the heartbeat last changed (or the clock started) */
  bool heard;            /* a heartbeat has been seen */
  uint8_t status;
  char status_text[MAILBOX_STATUS_ROOM];
} mailbox_client_t;

/* The module's mailbox (in its data, with the header filled in). */
mailbox_t *mailbox_shared(void);
/* A blank mailbox, as the module's starts (for the tests). */
void mailbox_blank(mailbox_t *box);
/* The seed this module runs, for the client to check it is the one it plays. */
void mailbox_set_seed(mailbox_t *box, const char *seed_id);
/* Starts the client's clock: it counts as silent from `now` until it is heard. */
void mailbox_start(mailbox_client_t *client, uint64_t now);
/* The client's new entries into `log` and its status into `client`, if a whole write can be read now (none is
 * while the sequence is odd or changes during the read: the next frame tries again). True if anything changed. */
bool mailbox_poll(mailbox_t *box, mailbox_client_t *client, console_log_t *log, uint64_t now);
/* The console's status line for the client's state at `now` (empty: none): "Archipelago client not running" when
 * it has been silent for MAILBOX_SILENT_MS (for an Archipelago seed, or once it was heard), else while it isn't
 * connected. */
#define MAILBOX_SILENT_MS 10000
void mailbox_status_line(const mailbox_client_t *client, bool archipelago, uint64_t now, char *out, size_t room);

#endif
