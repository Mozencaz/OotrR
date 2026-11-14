# ootrTracker: the in-game randomizer tracker module (src/). See docs/BUILDING.md.
# Lives in ingame_tracker/ of the OotrR repository (GPL-3, unlike the rest of it).
# Adapted from ocarinaMIDI's Makefile (c599fa5), which is adapted from sloperinaGZ's (GPL-3).
#
#   make            build bin/subsdk7
#   make dist       stage install trees in dist/ (emulator/, atmosphere/)
#   make ship       build, then copy bin/subsdk7 to the randomizer's resources and print its size and sha256 (for SOURCE.md there)
#   make test       the PC tests of the seed file, the tracker, the game data and the controls (Python 3 and a C compiler for the PC)
#   make clean
#
# Needs devkitA64 (DEVKITPRO set, e.g. devkitPro's MSYS2 shell) and Python 3 for the tests.

PACKAGE_VERSION      ?= $(shell cat VERSION 2>/dev/null || echo 0) ($(shell git describe --tags --always --dirty 2>/dev/null || echo unknown))
DEVKITPRO            ?= /opt/devkitpro
TOOLS                 = $(DEVKITPRO)/devkitA64/bin/aarch64-none-elf-
CC                    = $(TOOLS)gcc
ELF2NSO               = $(DEVKITPRO)/tools/bin/elf2nso
PYTHON               ?= python3

PROGRAM_ID            = 0400486024DEC000
SUBSDK                = subsdk7
NAME                  = ootrTracker

SRCDIR                = src
LDSCRIPT              = lib/module.ld
OBJDIR                = obj
BINDIR                = bin
DISTDIR               = dist

ARCHFLAGS             = -march=armv8-a+crc+crypto -mtune=cortex-a78 -mtp=soft -fPIC
CFLAGS                = -std=gnu11 -O2 -g -Wall -Wextra -Wno-unused-parameter $(ARCHFLAGS) \
                        -fvisibility=hidden -ffunction-sections -fdata-sections \
                        -fno-asynchronous-unwind-tables -fno-unwind-tables \
                        -fno-stack-protector -fno-plt -fno-common \
                        -DPACKAGE_VERSION='"$(PACKAGE_VERSION)"'
ASFLAGS               = $(ARCHFLAGS)
LDFLAGS               = -shared -nostdlib -nostartfiles -T $(LDSCRIPT) \
                        -Wl,--gc-sections -Wl,-z,text -Wl,-z,max-page-size=0x1000 \
                        -Wl,--hash-style=sysv -Wl,-Bsymbolic -Wl,--build-id=sha1 \
                        -Wl,-init=ootr_tracker_module_init -Wl,--exclude-libs=ALL
LDLIBS                = -lgcc

CSRC                  = $(wildcard $(SRCDIR)/*.c)
SSRC                  = $(wildcard $(SRCDIR)/*.S)
HDRS                  = $(wildcard $(SRCDIR)/*.h) $(wildcard $(SRCDIR)/third_party/*) # third_party/*.c are #included
OBJS                  = $(patsubst $(SRCDIR)/%,$(OBJDIR)/%.o,$(basename $(SSRC) $(CSRC)))

all: $(BINDIR)/$(SUBSDK)

$(OBJDIR)/%.o: $(SRCDIR)/%.c $(HDRS) | $(OBJDIR)
	$(CC) $(CFLAGS) -c $< -o $@
$(OBJDIR)/%.o: $(SRCDIR)/%.S | $(OBJDIR)
	$(CC) $(ASFLAGS) -c $< -o $@
$(BINDIR)/$(NAME).elf: $(OBJS) $(LDSCRIPT) | $(BINDIR)
	$(CC) $(ARCHFLAGS) $(LDFLAGS) -o $@ $(OBJS) $(LDLIBS)
	@# Reject undefined symbols the game's loader cannot resolve.
	@missing=$$($(TOOLS)readelf --dyn-syms -W $@ | awk '$$7=="UND" && $$8!="" {print $$8}' | LC_ALL=C sort -u | LC_ALL=C comm -23 - lib/imports.txt); \
	if [ -n "$$missing" ]; then echo "error: not defined, and not a known import (lib/imports.txt):"; echo "$$missing"; rm -f $@; exit 1; fi
$(BINDIR)/$(SUBSDK): $(BINDIR)/$(NAME).elf
	$(ELF2NSO) $< $@
$(OBJDIR) $(BINDIR):
	mkdir -p $@

# Install trees:
#   emulator/load/<program id>/ootrTracker/exefs/subsdk7  (Ryuchii / Eden: <user>/load/...; the randomizer puts it in each seed's folder)
#   atmosphere/contents/<program id>/exefs/subsdk7
dist: all
	rm -rf $(DISTDIR)
	mkdir -p $(DISTDIR)/emulator/load/$(PROGRAM_ID)/$(NAME)/exefs $(DISTDIR)/atmosphere/contents/$(PROGRAM_ID)/exefs
	cp $(BINDIR)/$(SUBSDK) $(DISTDIR)/emulator/load/$(PROGRAM_ID)/$(NAME)/exefs/
	cp $(BINDIR)/$(SUBSDK) $(DISTDIR)/atmosphere/contents/$(PROGRAM_ID)/exefs/

SHIPPED               = ../src/oot_rando/resources/ingame_tracker/subsdk7

ship: all
	cp $(BINDIR)/$(SUBSDK) $(SHIPPED)
	@sha256sum $(SHIPPED); wc -c < $(SHIPPED)

test:
	$(PYTHON) -I -m unittest discover -s tests -t .

clean:
	rm -rf $(OBJDIR) $(BINDIR) $(DISTDIR)

.PHONY: all dist ship test clean
