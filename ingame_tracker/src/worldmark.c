/* The check shown in the world, over the picture (see worldmark.h). The camera's and Link's offsets are
 * sloperinaGZ's (src/ootgz/link.c, view.c; 8a2c73c), the box's edges its airwall.c add_box's and the glow under each
 * line its overlayui.c draw_lines' (LINE_W, GLOW_W, GLOW_ALPHA). */
#include "worldmark.h"

#include "gpuui.h"
#include "sys.h"

float tanf(float x); /* from the sdk (lib/imports.txt) */

/* the game's camera: the camera manager's active camera, and in it (sloperinaGZ's view.c) */
#define CAMERA_MANAGER_CAMERA 0x68
#define CAM_POSITION          0x38
#define CAM_LOOK_AT           0x44
#define CAM_NEAR              0x128
#define CAM_FOV_Y             0x130
#define CAM_ASPECT            0x140
#define MIN_FOV               0.1f /* radians: sloperinaGZ's view_camera's limits */
#define MAX_FOV               3.0f
#define DISP_POSITION         0x29C /* Link's drawn position (sloperinaGZ's link.c link_drawn_pos) */

/* the marker: a box round the place (an actor's position is its base), a beam above it; widths at 1080 lines */
#define BOX_HALF_M        0.5f
#define BOX_HEIGHT_M      1.0f
#define BEAM_M            30.0f
#define LINE_PX           2.4f
#define GLOW_PX           9.0f
#define GLOW_ALPHA        0.22f
#define REFERENCE_HEIGHT  1080.0f

static const gpu_colour_t marker_colour = { 0.96f, 0.84f, 0.52f, 1 }; /* the panel's gold (title_colour) */

static float read_float(uintptr_t at)
{
  return *(const volatile float *)at;
}

bool worldmark_camera(uintptr_t camera_holder, view_cam_t *cam)
{
  uintptr_t manager = camera_holder ? sys_ptr(camera_holder) : 0;
  uintptr_t game_cam = manager ? sys_ptr(manager + CAMERA_MANAGER_CAMERA) : 0;
  if (!game_cam || !sys_mapped(game_cam + CAM_POSITION, CAM_ASPECT - CAM_POSITION + 4, SYS_PERM_R))
    return false;
  float pos[3], look[3];
  for (int i = 0; i < 3; i++) {
    pos[i] = read_float(game_cam + CAM_POSITION + 4 * i);
    look[i] = read_float(game_cam + CAM_LOOK_AT + 4 * i);
  }
  float fov = read_float(game_cam + CAM_FOV_Y);
  if (!(fov > MIN_FOV && fov < MAX_FOV))
    return false;
  return view_from(cam, pos, look, tanf(fov / 2), read_float(game_cam + CAM_ASPECT), read_float(game_cam + CAM_NEAR));
}

bool worldmark_link(uintptr_t link_holder, float out[3])
{
  uintptr_t disp = link_holder ? sys_ptr(link_holder) : 0;
  disp = disp ? sys_ptr(disp) : 0;
  if (!disp || !sys_mapped(disp + DISP_POSITION, 12, SYS_PERM_R))
    return false;
  for (int i = 0; i < 3; i++)
    out[i] = read_float(disp + DISP_POSITION + 4 * i);
  return out[0] == out[0] && out[1] == out[1] && out[2] == out[2]; /* not a NaN */
}

static void line(const view_cam_t *cam, const float a[3], const float b[3], float w, float h, bool glow)
{
  float s[4];
  if (!view_segment(cam, a, b, s))
    return;
  gpu_colour_t colour = marker_colour;
  colour.a = glow ? GLOW_ALPHA : 1;
  float px = h / REFERENCE_HEIGHT;
  gpuui_line(s[0] * w, s[1] * h, s[2] * w, s[3] * h, (glow ? GLOW_PX : LINE_PX) * px, colour);
}

void worldmark_draw(const view_cam_t *cam, const float point[3], float w, float h)
{
  float corner[8][3];
  for (int i = 0; i < 8; i++) {
    corner[i][0] = point[0] + (i & 1 ? BOX_HALF_M : -BOX_HALF_M);
    corner[i][1] = point[1] + (i & 2 ? BOX_HEIGHT_M : 0);
    corner[i][2] = point[2] + (i & 4 ? BOX_HALF_M : -BOX_HALF_M);
  }
  float top[3] = { point[0], point[1] + BOX_HEIGHT_M, point[2] };
  float sky[3] = { point[0], point[1] + BEAM_M, point[2] };
  for (int pass = 0; pass < 2; pass++) { /* the glows first, then the lines over them */
    bool glow = pass == 0;
    for (int i = 0; i < 8; i++)
      for (int axis = 0; axis < 3; axis++)
        if (!(i & (1 << axis)))
          line(cam, corner[i], corner[i | (1 << axis)], w, h, glow);
    line(cam, top, sky, w, h, glow);
  }
}
