/* The game's camera, for drawing a check's place in the world over the picture ("show in the world", locate.h).
 * The camera basis and the projection are sloperinaGZ's src/ootgz/view.c, the cutting of a segment at the near
 * plane and to the picture its src/ootgz/airwall.c clip_near and clip_to_picture (GPL-3; 8a2c73c). Pure: the
 * camera's numbers are read from the game by worldmark.c, so the tests run this on the PC. */
#ifndef VIEW_H
#define VIEW_H

#include <stdbool.h>

#define VIEW_DEFAULT_NEAR 0.1f /* metres: the near plane when the game's isn't sane (sloperinaGZ's DEFAULT_NEAR) */

typedef struct {
  float pos[3], forward[3], right[3], up[3];
  float tan_x, tan_y; /* tangents of half the horizontal and vertical fov */
  float near;         /* metres ahead where the picture starts */
} view_cam_t;

typedef enum { VIEW_ON_PICTURE, VIEW_LEFT, VIEW_RIGHT, VIEW_ABOVE, VIEW_BELOW, VIEW_BEHIND } view_side_t;

/* The camera from its position, the point it looks at, the tangent of half its vertical fov and its aspect (width
 * over height), as the game holds them; false if they don't make one (the look-at on the position, looking
 * straight up or down, the fov or the aspect out of range). */
bool view_from(view_cam_t *cam, const float pos[3], const float look[3], float tan_half_fov_y, float aspect,
               float near);
/* world point x in camera space: (right, up, forward) */
void view_point(const view_cam_t *cam, const float x[3], float v[3]);
/* camera-space point to 0..1 across and down the picture (v[2] must be in front of the camera) */
void view_screen(const view_cam_t *cam, const float v[3], float *sx, float *sy);
/* The world segment a-b on the picture as (x0, y0, x1, y1), 0..1 across and down, cut at the near plane and to the
 * picture; false if none of it is on the picture. */
bool view_segment(const view_cam_t *cam, const float a[3], const float b[3], float out[4]);
/* Where world point x is seen from the camera: on the picture, or the way to turn to see it. */
view_side_t view_side(const view_cam_t *cam, const float x[3]);
/* The length of v, and the square root it takes (the CPU's instruction on the console: the module imports no sqrtf). */
float view_length(const float v[3]);
float view_root(float v);

#endif
