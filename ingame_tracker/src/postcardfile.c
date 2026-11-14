#include "postcardfile.h"

#include "nnfs.h"
#include "sys.h"

#define SD_MOUNT      "ootrtrk" /* a mount name can only be used once: not sloperinaGZ's or ocarinaMIDI's */
#define SD_DIR        SD_MOUNT ":/ootrTracker"
#define SETTINGS_FILE SD_DIR "/postcard.cfg"
#define FILE_ROOM     128 /* the four short lines */

static bool sd_mounted;

static bool mount_sd(void)
{
  if (sd_mounted)
    return true;
  nn_result_t result = fs_mount_sd(SD_MOUNT);
  if (result != 0)
    result = fs_mount_sd_debug(SD_MOUNT);
  if (result != 0) {
    log_printf("postcard: no SD card access (0x%x): the settings won't be kept", (unsigned)result);
    return false;
  }
  sd_mounted = true;
  return true;
}

void postcardfile_load(postcard_settings_t *settings)
{
  if (!mount_sd())
    return;
  fs_file_t file;
  if (fs_open(&file, SETTINGS_FILE, FS_READ) != 0) {
    log_printf("postcard: no " SETTINGS_FILE ": the defaults");
    return;
  }
  char text[FILE_ROOM];
  int64_t size = 0;
  size_t got = 0;
  if (fs_size(&size, file) == 0 && size > 0 && size <= (int64_t)sizeof(text) &&
      fs_read(&got, file, 0, text, (size_t)size) == 0)
    postcard_parse(settings, text, got);
  else
    log_printf("postcard: " SETTINGS_FILE " can't be read: the defaults");
  fs_close(file);
}

bool postcardfile_save(const postcard_settings_t *settings)
{
  if (!sd_mounted)
    return false;
  char text[FILE_ROOM];
  size_t length = postcard_format(settings, text, sizeof(text));
  fs_file_t file;
  fs_write_option_t flush = { FS_WRITE_FLUSH };
  fs_create_dir(SD_DIR); /* fails harmlessly if it exists */
  fs_delete_file(SETTINGS_FILE);
  if (fs_create_file(SETTINGS_FILE, (int64_t)length) != 0 || fs_open(&file, SETTINGS_FILE, FS_WRITE) != 0) {
    log_printf("postcard: couldn't create " SETTINGS_FILE);
    return false;
  }
  nn_result_t result = fs_write(file, 0, text, length, &flush);
  fs_close(file);
  if (result != 0)
    log_printf("postcard: writing " SETTINGS_FILE " failed (0x%x)", (unsigned)result);
  return result == 0;
}
