#include "postcardfile.h"

#include "sdfile.h"

#define SETTINGS_FILE SDFILE_DIR "/postcard.cfg"
#define FILE_ROOM     128 /* the four short lines */

void postcardfile_load(postcard_settings_t *settings)
{
  char text[FILE_ROOM];
  size_t size;
  if (sdfile_read("postcard", SETTINGS_FILE, text, sizeof(text), &size))
    postcard_parse(settings, text, size);
}

bool postcardfile_save(const postcard_settings_t *settings)
{
  char text[FILE_ROOM];
  size_t length = postcard_format(settings, text, sizeof(text));
  return sdfile_write("postcard", SETTINGS_FILE, text, length);
}
