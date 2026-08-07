# q88measure — 計測ハーネスのフロントエンド
#
# コアは dlopen で開くのでリンクしない。必要なのはヘッダだけ。
# CORE_SRC は setup_harness.sh が用意した上流ツリー（既定は ../../../../vendor/...）

REPO      := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)
CORE_SRC  ?= $(abspath $(REPO)/..)/vendor/quasi88-libretro/src

CFLAGS  += -O2 -Wall -Wextra -std=c99 -D_POSIX_C_SOURCE=200809L
CFLAGS  += -I$(CORE_SRC)/LIBRETRO/libretro-common/include
CFLAGS  += -I$(REPO)/tools/harness/core
LDFLAGS += -ldl

TARGET  := q88measure

all: $(TARGET)

$(TARGET): main.c
	@test -d "$(CORE_SRC)" || { echo "コアのソースが無い: $(CORE_SRC)"; echo "先に tools/setup_harness.sh を実行すること"; exit 1; }
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f $(TARGET)

.PHONY: all clean
