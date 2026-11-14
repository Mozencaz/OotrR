/* Module header for a Horizon NSO loaded as subsdkN. Adapted from sloperinaGZ's src/ootgz/crt0.S (GPL-3).
 *
 * rtld finds MOD0 through the word at offset 4 of the module, relocates the module, links
 * its imports against the other modules (main, subsdk*, sdk) and calls DT_INIT (set to
 * ootr_tracker_module_init by the Makefile). The last MOD0 word points at bss space rtld uses
 * for its own module object; Switch 1 needs 0xD0 bytes, 0x200 leaves room for a larger
 * Switch 2 one.
 * Taken from ocarinaMIDI (c599fa5, GPL-3).
 */
.section .text.crt0, "ax", %progbits
.global __module_start
.hidden __module_start
__module_start:
  .word   0
  .word   __nx_mod0 - __module_start  /* offset 4: where rtld finds MOD0 */
  .ascii  "OOTRTRK\0"

.section .rodata.mod0, "a", %progbits
.align  2
.global __nx_mod0
.hidden __nx_mod0
__nx_mod0:
  .ascii  "MOD0"
  .word   __dynamic_start__       - __nx_mod0
  .word   __bss_start__           - __nx_mod0
  .word   __bss_end__             - __nx_mod0
  .word   __eh_frame_hdr_start__  - __nx_mod0
  .word   __eh_frame_hdr_end__    - __nx_mod0
  .word   __nx_module_runtime     - __nx_mod0

.section .bss.module_runtime, "aw", %nobits
.align  3
.global __nx_module_runtime
.hidden __nx_module_runtime
__nx_module_runtime:
  .space  0x200
