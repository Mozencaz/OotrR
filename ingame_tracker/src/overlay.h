/* The panel and the console on screen: over the game's picture, drawn before each of the game's presents.
 * app.c says what it holds; trackerui.c draws it in the game's own style.
 * Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#ifndef OVERLAY_H
#define OVERLAY_H

#include "consolelog.h"
#include "locate.h"
#include "panel.h"

/* What the panel shows from now on (copied; from the one thread that calls it). */
void overlay_publish(const panel_t *panel);
/* What the console shows from now on (copied; from the same thread). */
void overlay_publish_console(const console_view_t *view);
/* The check shown in the world from now on (copied; from the same thread). */
void overlay_publish_locate(const locate_view_t *view);

#endif
