/* The module can't rename a file (nn::fs::RenameFile isn't among the sdk functions it is known to call), so a save
 * writes the text to the copy (.new) first, then to the file, then deletes the copy: a write cut off leaves one of
 * the two whole, and a load reads the file, or the copy if the file is missing or damaged. */
#include "marksfile.h"

#include "sdfile.h"
#include "sys.h"

void *aligned_alloc(size_t align, size_t size); /* from main */
void free(void *p);                             /* from main */

#define TEXT_ALIGN 16
#define PATH_ROOM  96

static bool paths(const trk_t *trk, char file[PATH_ROOM], char copy[PATH_ROOM])
{
  size_t dir = sizeof(SDFILE_DIR "/") - 1;
  memcpy(file, SDFILE_DIR "/", dir);
  memcpy(copy, SDFILE_DIR "/", dir);
  return marks_file_name(trk, false, file + dir, PATH_ROOM - dir) &&
         marks_file_name(trk, true, copy + dir, PATH_ROOM - dir);
}

static bool read_into(marks_t *marks, const trk_t *trk, const char *path, char *text)
{
  size_t size;
  if (!sdfile_read("marks", path, text, MARKS_FILE_ROOM, &size))
    return false;
  if (marks_parse(marks, trk, text, size))
    return true;
  log_printf("marks: %s is damaged or another seed's: left out", path);
  return false;
}

void marksfile_load(marks_t *marks, const trk_t *trk)
{
  char file[PATH_ROOM], copy[PATH_ROOM];
  if (marks->state == MARKS_OLD_FILE) {
    log_printf("marks: the seed file has no checks' ids (version %u): nothing can be ticked", (unsigned)trk->version);
    return;
  }
  if (marks->state != MARKS_ON || !paths(trk, file, copy)) {
    log_printf("marks: this seed file's ids can't be kept: nothing can be ticked");
    return;
  }
  char *text = aligned_alloc(TEXT_ALIGN, MARKS_FILE_ROOM);
  if (!text) {
    log_printf("marks: no memory to read them");
    return;
  }
  if (read_into(marks, trk, file, text) || read_into(marks, trk, copy, text))
    log_printf("marks: %u checks ticked by hand", (unsigned)marks->count);
  free(text);
}

bool marksfile_save(const marks_t *marks, const trk_t *trk)
{
  char file[PATH_ROOM], copy[PATH_ROOM];
  if (marks->state != MARKS_ON || !paths(trk, file, copy))
    return false;
  char *text = aligned_alloc(TEXT_ALIGN, MARKS_FILE_ROOM);
  if (!text) {
    log_printf("marks: no memory to write them");
    return false;
  }
  size_t length = marks_format(marks, trk, text, MARKS_FILE_ROOM);
  bool saved = length && sdfile_write("marks", copy, text, length) && sdfile_write("marks", file, text, length);
  if (saved)
    sdfile_delete(copy);
  free(text);
  return saved;
}
