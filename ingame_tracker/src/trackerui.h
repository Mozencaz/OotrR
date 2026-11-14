/* The tracker panel in the game's own style: its UI font (Clarimo UD PE), its UI shader and the dark box and gold
 * title its menus have, drawn on the GPU by gpuui.c. The font and the shader are read from the game's RomFS when
 * the panel is first wanted; nothing of them ships with this module. The look follows sloperinaGZ's menu in its
 * game style (src/ootgz/nativeui.c, GPL-3; master 8c3a940636), through ocarinaMIDI's gameui.c (c599fa5). */
#ifndef TRACKERUI_H
#define TRACKERUI_H

#include <stdbool.h>

#include "nvn.h"
#include "panel.h"

/* Game thread, once (later calls do nothing): reads the game's font and shader. Takes a moment, and some
 * of the game's heap, so it's left until the panel is first opened. */
void trackerui_load(void);
/* Render thread: whether the panel can be drawn now (the first time after a successful trackerui_load, sets
 * up the GPU side). */
bool trackerui_usable(void);
/* Records the panel into `cmd` (a slot's, slots.h); false if there is nothing to draw. */
bool trackerui_record(nvn_obj_t *cmd, int slot, nvn_texture_t *texture, const nvn_texture_info_t *info,
                      nvn_rect_t area, const panel_t *panel);

#endif
