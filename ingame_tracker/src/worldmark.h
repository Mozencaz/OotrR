/* The check shown in the world (locate.h), drawn over the picture: a box round its place and a beam up from it, in
 * lines that are not depth-tested (seen through walls), with the game's camera read the way sloperinaGZ reads it
 * (src/ootgz/link.c camera() and view.c view_camera, GPL-3; 8a2c73c). The reads are checked, like gamedata.c's. */
#ifndef WORLDMARK_H
#define WORLDMARK_H

#include <stdbool.h>
#include <stdint.h>

#include "view.h"

/* The game's camera this frame, from main + camera_ptr; false if it isn't readable or isn't a camera. */
bool worldmark_camera(uintptr_t camera_holder, view_cam_t *cam);
/* Link's drawn position, from main + disp_ptr; false if it isn't readable. */
bool worldmark_link(uintptr_t link_holder, float out[3]);
/* The marker of the place `point` on a picture w x h pixels (between gpuui_begin and gpuui_end). */
void worldmark_draw(const view_cam_t *cam, const float point[3], float w, float h);

#endif
