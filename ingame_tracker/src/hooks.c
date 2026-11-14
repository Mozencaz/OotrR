/* Taken from ocarinaMIDI (c599fa5, GPL-3). */
#include "hooks.h"

#include <stdbool.h>

#include "got.h"
#include "poll.h"
#include "sys.h"

#define GET_NPAD_STATES(style) "_ZN2nn3hid13GetNpadStatesEPNS0_" style "EiRKj"
#define INITIALIZE_NPAD        "_ZN2nn3hid14InitializeNpadEv"
#define GET_NPAD_STYLE_SET     "_ZN2nn3hid15GetNpadStyleSetERKj"

typedef struct { uint32_t bits; } npad_style_set_t; /* nn::hid::NpadStyleSet: one 32-bit flag set */
typedef int (*get_npad_states_t)(void *out, int count, const uint32_t *npad_id);
typedef void (*initialize_npad_t)(void);
typedef npad_style_set_t (*get_npad_style_set_t)(const uint32_t *npad_id);

/* The sdk's own functions, imported by this module too (rtld binds this module's imports before
 * any module's init): what a hook calls while main's slot for it isn't bound yet. */
void sdk_initialize_npad(void) __asm__(INITIALIZE_NPAD);
npad_style_set_t sdk_get_npad_style_set(const uint32_t *npad_id) __asm__(GET_NPAD_STYLE_SET);
int sdk_get_states_full_key(void *, int, const uint32_t *) __asm__(GET_NPAD_STATES("16NpadFullKeyState"));
int sdk_get_states_handheld(void *, int, const uint32_t *) __asm__(GET_NPAD_STATES("17NpadHandheldState"));
int sdk_get_states_joy_dual(void *, int, const uint32_t *) __asm__(GET_NPAD_STATES("16NpadJoyDualState"));
int sdk_get_states_joy_left(void *, int, const uint32_t *) __asm__(GET_NPAD_STATES("16NpadJoyLeftState"));
int sdk_get_states_joy_right(void *, int, const uint32_t *) __asm__(GET_NPAD_STATES("17NpadJoyRightState"));

enum { STYLE_FULL_KEY, STYLE_HANDHELD, STYLE_JOY_DUAL, STYLE_JOY_LEFT, STYLE_JOY_RIGHT, STYLE_COUNT };

static uintptr_t game_main;
/* What each hook calls; got_hook fills them in before pointing the slot at the hook. */
static void *next_get_states[STYLE_COUNT];
static void *next_initialize_npad;
static void *next_get_style_set;

#define GET_STATES_WRAPPER(style)                                                     \
  static int get_states_##style(void *out, int count, const uint32_t *npad_id)       \
  {                                                                                   \
    int read = ((get_npad_states_t)next_get_states[style])(out, count, npad_id);      \
    if (read > 0)                                                                     \
      poll_states(style, *npad_id, out, read < count ? read : count);                 \
    return read;                                                                      \
  }
GET_STATES_WRAPPER(STYLE_FULL_KEY)
GET_STATES_WRAPPER(STYLE_HANDHELD)
GET_STATES_WRAPPER(STYLE_JOY_DUAL)
GET_STATES_WRAPPER(STYLE_JOY_LEFT)
GET_STATES_WRAPPER(STYLE_JOY_RIGHT)

static const struct {
  const char *import;
  void *function;
  void *wrapper;
} styles[STYLE_COUNT] = {
  [STYLE_FULL_KEY] = { GET_NPAD_STATES("16NpadFullKeyState"), sdk_get_states_full_key, get_states_STYLE_FULL_KEY },
  [STYLE_HANDHELD] = { GET_NPAD_STATES("17NpadHandheldState"), sdk_get_states_handheld, get_states_STYLE_HANDHELD },
  [STYLE_JOY_DUAL] = { GET_NPAD_STATES("16NpadJoyDualState"), sdk_get_states_joy_dual, get_states_STYLE_JOY_DUAL },
  [STYLE_JOY_LEFT] = { GET_NPAD_STATES("16NpadJoyLeftState"), sdk_get_states_joy_left, get_states_STYLE_JOY_LEFT },
  [STYLE_JOY_RIGHT] = { GET_NPAD_STATES("17NpadJoyRightState"), sdk_get_states_joy_right, get_states_STYLE_JOY_RIGHT },
};

/* What a hook calls: the sdk's function, or another module's wrapper. */
static const char *next_owner(void *next)
{
  uintptr_t sdk_code = sys_region_start((uintptr_t)&memcpy);
  return sys_region_start((uintptr_t)next) == sdk_code ? "the sdk" : "another module";
}

static void hook_controller_reads(const char *trigger)
{
  static bool hooked;
  if (__atomic_load_n(&hooked, __ATOMIC_ACQUIRE) || __atomic_exchange_n(&hooked, true, __ATOMIC_ACQ_REL))
    return;
  for (int style = 0; style < STYLE_COUNT; style++) {
    const char *error =
      got_hook(game_main, styles[style].import, styles[style].wrapper, styles[style].function, &next_get_states[style]);
    if (error) {
      log_printf("GetNpadStates style %d: %s", style, error);
      continue;
    }
    void *next = next_get_states[style];
    log_printf("GetNpadStates style %d hooked from %s: calls %s at 0x%lx", style, trigger, next_owner(next),
               (unsigned long)(uintptr_t)next);
  }
}

static void initialize_npad_hook(void)
{
  ((initialize_npad_t)next_initialize_npad)();
  hook_controller_reads("InitializeNpad");
}

static npad_style_set_t get_style_set_hook(const uint32_t *npad_id)
{
  hook_controller_reads("GetNpadStyleSet");
  return ((get_npad_style_set_t)next_get_style_set)(npad_id);
}

const char *hooks_init(uintptr_t main_base)
{
  game_main = main_base;
  const char *initialize_error =
    got_hook(main_base, INITIALIZE_NPAD, initialize_npad_hook, sdk_initialize_npad, &next_initialize_npad);
  const char *style_set_error =
    got_hook(main_base, GET_NPAD_STYLE_SET, get_style_set_hook, sdk_get_npad_style_set, &next_get_style_set);
  return initialize_error && style_set_error ? initialize_error : 0;
}
