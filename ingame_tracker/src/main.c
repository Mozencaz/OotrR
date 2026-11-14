/* ootrTracker: shows what a randomizer seed's save has found, in the game's own style, over the game of
 * Ocarina of Time (Switch 2, program id 0400486024DEC000). Loaded by the game as subsdk7; see docs/DESIGN.md.
 * Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#include "app.h"
#include "hooks.h"
#include "nvn.h"
#include "sys.h"

/* exported by main */
extern void nnMain(void);

__attribute__((used)) void ootr_tracker_module_init(void)
{
  uintptr_t main_base = sys_region_start((uintptr_t)&nnMain);
  const char *error = main_base ? hooks_init(main_base) : "the game's main module wasn't found";
  if (error) {
    log_raw("not started:");
    log_raw(error);
    return;
  }
  app_init((uintptr_t)&nnMain);
  /* at init, unlike the controller hooks: the game may set up NVN before its first controller call */
  const char *no_panel = nvn_hook_game(main_base);
  if (no_panel) {
    log_raw("no panel on screen:");
    log_raw(no_panel);
  }
  log_raw("loaded " PACKAGE_VERSION "; controller hooks go in at the game's first controller setup");
}
