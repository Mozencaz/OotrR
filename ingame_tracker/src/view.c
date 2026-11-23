/* The game's camera, for drawing a check's place over the picture (see view.h). From sloperinaGZ's
 * src/ootgz/view.c and src/ootgz/airwall.c (GPL-3; 8a2c73c). */
#include "view.h"

#define MIN_TAN      0.05f /* half a fov of 0.1 radians: sloperinaGZ's view_camera's limits (0.1 to 3 radians) */
#define MAX_TAN      14.2f
#define MIN_ASPECT   0.5f
#define MAX_ASPECT   4.0f
#define MIN_LENGTH   1e-4f
#define MIN_NEAR     0.001f /* sloperinaGZ's view_camera's sane near plane */
#define MAX_NEAR     10.0f

float view_root(float v)
{
  if (!(v > 0))
    return 0;
#if defined(__aarch64__)
  float r;
  __asm__("fsqrt %s0, %s1" : "=w"(r) : "w"(v));
  return r;
#else
  float r = v > 1 ? v / 2 : 1; /* Newton's method, for the PC tests (no libm) */
  for (int i = 0; i < 48; i++)
    r = (r + v / r) / 2;
  return r;
#endif
}

float view_length(const float v[3])
{
  return view_root(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

bool view_from(view_cam_t *cam, const float pos[3], const float look[3], float tan_half_fov_y, float aspect,
               float near)
{
  if (!(tan_half_fov_y > MIN_TAN && tan_half_fov_y < MAX_TAN) || !(aspect > MIN_ASPECT && aspect < MAX_ASPECT))
    return false;
  float f[3] = { look[0] - pos[0], look[1] - pos[1], look[2] - pos[2] };
  float f_len = view_length(f);
  if (!(f_len >= MIN_LENGTH))
    return false;
  for (int i = 0; i < 3; i++) {
    cam->pos[i] = pos[i];
    cam->forward[i] = f[i] / f_len;
  }
  float r[3] = { -cam->forward[2], 0, cam->forward[0] }; /* forward x world up */
  float r_len = view_length(r);
  if (!(r_len >= MIN_LENGTH))
    return false;
  cam->right[0] = r[0] / r_len;
  cam->right[1] = 0;
  cam->right[2] = r[2] / r_len;
  /* up = right x forward */
  cam->up[0] = cam->right[1] * cam->forward[2] - cam->right[2] * cam->forward[1];
  cam->up[1] = cam->right[2] * cam->forward[0] - cam->right[0] * cam->forward[2];
  cam->up[2] = cam->right[0] * cam->forward[1] - cam->right[1] * cam->forward[0];
  cam->tan_y = tan_half_fov_y;
  cam->tan_x = tan_half_fov_y * aspect;
  cam->near = near > MIN_NEAR && near < MAX_NEAR ? near : VIEW_DEFAULT_NEAR;
  return true;
}

void view_point(const view_cam_t *cam, const float x[3], float v[3])
{
  float d[3] = { x[0] - cam->pos[0], x[1] - cam->pos[1], x[2] - cam->pos[2] };
  v[0] = d[0] * cam->right[0] + d[1] * cam->right[1] + d[2] * cam->right[2];
  v[1] = d[0] * cam->up[0] + d[1] * cam->up[1] + d[2] * cam->up[2];
  v[2] = d[0] * cam->forward[0] + d[1] * cam->forward[1] + d[2] * cam->forward[2];
}

void view_screen(const view_cam_t *cam, const float v[3], float *sx, float *sy)
{
  *sx = (v[0] / (v[2] * cam->tan_x) + 1) / 2;
  *sy = (1 - v[1] / (v[2] * cam->tan_y)) / 2;
}

/* the segment va-vb (camera space) cut where it goes behind the near plane; false if all of it is behind */
static bool clip_near(float va[3], float vb[3], float near)
{
  if (va[2] < near && vb[2] < near)
    return false;
  if (va[2] < near || vb[2] < near) {
    float t = (near - va[2]) / (vb[2] - va[2]);
    float cut[3];
    for (int i = 0; i < 3; i++)
      cut[i] = va[i] + t * (vb[i] - va[i]);
    float *behind = va[2] < near ? va : vb;
    for (int i = 0; i < 3; i++)
      behind[i] = cut[i];
  }
  return true;
}

/* the segment s (x0, y0, x1, y1) cut to the picture, 0..1 both ways (Liang-Barsky); false if it's all outside */
static bool clip_to_picture(float s[4])
{
  float dx = s[2] - s[0], dy = s[3] - s[1];
  float t0 = 0, t1 = 1;
  float p[4] = { -dx, dx, -dy, dy };
  float q[4] = { s[0], 1 - s[0], s[1], 1 - s[1] };
  for (int i = 0; i < 4; i++) {
    if (p[i] == 0) {
      if (q[i] < 0)
        return false;
      continue;
    }
    float r = q[i] / p[i];
    if (p[i] < 0) {
      if (r > t1)
        return false;
      if (r > t0)
        t0 = r;
    } else {
      if (r < t0)
        return false;
      if (r < t1)
        t1 = r;
    }
  }
  float x0 = s[0], y0 = s[1];
  s[0] = x0 + t0 * dx;
  s[1] = y0 + t0 * dy;
  s[2] = x0 + t1 * dx;
  s[3] = y0 + t1 * dy;
  return true;
}

bool view_segment(const view_cam_t *cam, const float a[3], const float b[3], float out[4])
{
  float va[3], vb[3];
  view_point(cam, a, va);
  view_point(cam, b, vb);
  if (!clip_near(va, vb, cam->near))
    return false;
  view_screen(cam, va, &out[0], &out[1]);
  view_screen(cam, vb, &out[2], &out[3]);
  return clip_to_picture(out);
}

view_side_t view_side(const view_cam_t *cam, const float x[3])
{
  float v[3], sx, sy;
  view_point(cam, x, v);
  if (v[2] < cam->near)
    return VIEW_BEHIND;
  view_screen(cam, v, &sx, &sy);
  float off_x = sx < 0 ? -sx : sx > 1 ? sx - 1 : 0, off_y = sy < 0 ? -sy : sy > 1 ? sy - 1 : 0;
  if (!off_x && !off_y)
    return VIEW_ON_PICTURE;
  if (off_x >= off_y)
    return sx < 0 ? VIEW_LEFT : VIEW_RIGHT;
  return sy < 0 ? VIEW_ABOVE : VIEW_BELOW;
}
