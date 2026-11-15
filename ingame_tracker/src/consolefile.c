#include "consolefile.h"

#include "sdfile.h"

#define SETTINGS_FILE SDFILE_DIR "/console.cfg"
#define FILE_ROOM     256 /* thirteen short lines */

void consolefile_load(console_settings_t *settings)
{
  char text[FILE_ROOM];
  size_t size;
  if (sdfile_read("console", SETTINGS_FILE, text, sizeof(text), &size))
    console_parse(settings, text, size);
}

bool consolefile_save(const console_settings_t *settings)
{
  char text[FILE_ROOM];
  size_t length = console_format(settings, text, sizeof(text));
  return sdfile_write("console", SETTINGS_FILE, text, length);
}
