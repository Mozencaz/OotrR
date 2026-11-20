#include "sdfile.h"

#include "nnfs.h"
#include "sys.h"

#define SD_MOUNT "ootrtrk"

static enum { SD_UNTRIED, SD_MOUNTED, SD_MISSING } sd_state;

static bool mount_sd(void)
{
  if (sd_state != SD_UNTRIED)
    return sd_state == SD_MOUNTED;
  nn_result_t result = fs_mount_sd(SD_MOUNT);
  if (result != 0)
    result = fs_mount_sd_debug(SD_MOUNT);
  sd_state = result == 0 ? SD_MOUNTED : SD_MISSING;
  if (result != 0)
    log_printf("settings: no SD card access (0x%x): the postcard's and the console's settings and the ticks won't be "
               "kept", (unsigned)result);
  return sd_state == SD_MOUNTED;
}

bool sdfile_read(const char *who, const char *path, char *text, size_t room, size_t *size)
{
  *size = 0;
  if (!mount_sd())
    return false;
  fs_file_t file;
  if (fs_open(&file, path, FS_READ) != 0) {
    log_printf("%s: no %s: the defaults", who, path);
    return false;
  }
  int64_t file_size = 0;
  bool read = fs_size(&file_size, file) == 0 && file_size > 0 && file_size <= (int64_t)room &&
              fs_read(size, file, 0, text, (size_t)file_size) == 0;
  fs_close(file);
  if (!read) {
    log_printf("%s: %s can't be read: the defaults", who, path);
    *size = 0;
  }
  return read;
}

bool sdfile_write(const char *who, const char *path, const char *text, size_t length)
{
  if (sd_state != SD_MOUNTED)
    return false;
  fs_file_t file;
  fs_write_option_t flush = { FS_WRITE_FLUSH };
  fs_create_dir(SDFILE_DIR); /* fails harmlessly if it exists */
  fs_delete_file(path);
  if (fs_create_file(path, (int64_t)length) != 0 || fs_open(&file, path, FS_WRITE) != 0) {
    log_printf("%s: couldn't create %s", who, path);
    return false;
  }
  nn_result_t result = fs_write(file, 0, text, length, &flush);
  fs_close(file);
  if (result != 0)
    log_printf("%s: writing %s failed (0x%x)", who, path, (unsigned)result);
  return result == 0;
}

void sdfile_delete(const char *path)
{
  if (sd_state == SD_MOUNTED)
    fs_delete_file(path);
}
