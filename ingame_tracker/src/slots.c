/* See slots.h. Adapted from sloperinaGZ's src/ootgz/nvn.c (GPL-3).
 * Taken from ocarinaMIDI (c599fa5, GPL-3). */
#include "slots.h"

#include "sys.h"

void *aligned_alloc(size_t align, size_t size); /* from main */

#define CTRL_SIZE        0x4000 /* control memory per slot */
#define PAGE_SIZE        0x1000
#define SYNC_TIMEOUT_NS  1000000000ull /* a second: waiting for every slot */
#define SLOT_WAIT_NS     100000000ull  /* each frame's wait for its slot: a tenth of a second */
#define STUCK_MS         5000          /* a slot busy this long: the GPU is stuck */

enum {
  SYNC_ALL_GPU_COMMANDS_COMPLETE = 0, /* nvnQueueFenceSync's condition */
  SYNC_TIMEOUT_EXPIRED = 2,           /* nvnSyncWait: lower results mean the GPU got there */
};

static struct {
  bool (*cmd_init)(nvn_obj_t *, nvn_device_t *);
  void (*cmd_add_command)(nvn_obj_t *, const nvn_obj_t *pool, ptrdiff_t offset, size_t size);
  void (*cmd_add_control)(nvn_obj_t *, void *, size_t);
  void (*cmd_begin)(nvn_obj_t *);
  nvn_handle_t (*cmd_end)(nvn_obj_t *);
  void (*queue_submit)(nvn_queue_t *, int, const nvn_handle_t *);
  void (*queue_fence)(nvn_queue_t *, nvn_obj_t *sync, int condition, int flags);
  bool (*sync_init)(nvn_obj_t *, nvn_device_t *);
  int (*sync_wait)(const nvn_obj_t *, uint64_t timeout_ns);
} fn;

static const char *const fn_names[] = {
  "nvnCommandBufferInitialize", "nvnCommandBufferAddCommandMemory", "nvnCommandBufferAddControlMemory",
  "nvnCommandBufferBeginRecording", "nvnCommandBufferEndRecording", "nvnQueueSubmitCommands",
  "nvnQueueFenceSync", "nvnSyncInitialize", "nvnSyncWait",
};
#define FN_COUNT (sizeof(fn_names) / sizeof(*fn_names))
_Static_assert(FN_COUNT == sizeof(fn) / sizeof(void *), "fn table");

static nvn_obj_t cmd_buffer, command_pool, slot_sync[SLOT_COUNT];
static uint8_t *command_mem, *control_mem;
static size_t command_size;
static bool slot_used[SLOT_COUNT];
static unsigned frame_count;
static uint64_t waiting_since_ms; /* when a frame first found its slot still busy; 0: not waiting */

static bool load_functions(void)
{
  void **slots = (void **)&fn;
  for (unsigned i = 0; i < FN_COUNT; i++) {
    slots[i] = nvn_proc(fn_names[i]);
    if (!slots[i]) {
      log_printf("NVN has no %s", fn_names[i]);
      return false;
    }
  }
  return true;
}

bool slots_init(size_t command_bytes)
{
  command_size = command_bytes;
  if (!load_functions())
    return false;
  command_mem = aligned_alloc(PAGE_SIZE, command_size * SLOT_COUNT);
  control_mem = aligned_alloc(PAGE_SIZE, CTRL_SIZE * SLOT_COUNT);
  if (!command_mem || !control_mem) {
    log_printf("out of memory for the drawing's commands");
    return false;
  }
  if (!nvn_make_pool(&command_pool, command_mem, command_size * SLOT_COUNT,
                     NVN_POOL_CPU_UNCACHED | NVN_POOL_GPU_CACHED)) {
    log_printf("no memory pool for the drawing's commands");
    return false;
  }
  if (!fn.cmd_init(&cmd_buffer, nvn_device())) {
    log_printf("no command buffer for the drawing");
    return false;
  }
  for (int s = 0; s < SLOT_COUNT; s++) {
    if (!fn.sync_init(&slot_sync[s], nvn_device())) {
      log_printf("no fence for the drawing");
      return false;
    }
  }
  return true;
}

int slots_acquire(void)
{
  int slot = (int)(frame_count % SLOT_COUNT);
  if (slot_used[slot] && fn.sync_wait(&slot_sync[slot], SLOT_WAIT_NS) >= SYNC_TIMEOUT_EXPIRED) {
    if (!waiting_since_ms)
      waiting_since_ms = sys_ms() | 1;
    return -1;
  }
  waiting_since_ms = 0;
  frame_count++;
  return slot;
}

bool slots_stuck(void)
{
  return waiting_since_ms && sys_ms() - waiting_since_ms > STUCK_MS;
}

nvn_obj_t *slots_begin(int slot)
{
  fn.cmd_add_command(&cmd_buffer, &command_pool, (ptrdiff_t)slot * (ptrdiff_t)command_size, command_size);
  fn.cmd_add_control(&cmd_buffer, control_mem + (size_t)slot * CTRL_SIZE, CTRL_SIZE);
  fn.cmd_begin(&cmd_buffer);
  return &cmd_buffer;
}

void slots_submit(nvn_queue_t *queue, int slot)
{
  __asm__ volatile("dsb sy" ::: "memory"); /* what the commands read reaches memory before the GPU does */
  nvn_handle_t handle = fn.cmd_end(&cmd_buffer);
  fn.queue_submit(queue, 1, &handle);
  fn.queue_fence(queue, &slot_sync[slot], SYNC_ALL_GPU_COMMANDS_COMPLETE, 0);
  slot_used[slot] = true;
}

void slots_discard(void)
{
  fn.cmd_end(&cmd_buffer);
}

bool slots_wait_idle(void)
{
  for (int s = 0; s < SLOT_COUNT; s++)
    if (slot_used[s] && fn.sync_wait(&slot_sync[s], SYNC_TIMEOUT_NS) >= SYNC_TIMEOUT_EXPIRED)
      return false;
  return true;
}
