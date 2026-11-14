/* The panel on screen: one box over the game's picture, drawn before each of the game's presents.
 * app.c says what it holds; trackerui.c draws it in the game's own style.
 * Based on ocarinaMIDI's file of the same name (c599fa5, GPL-3). */
#ifndef OVERLAY_H
#define OVERLAY_H

#include "panel.h"

/* What the panel shows from now on (copied; from the one thread that calls it). */
void overlay_publish(const panel_t *panel);

#endif
