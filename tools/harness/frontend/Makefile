# q88measure — 計測ハーネスのフロントエンド
#
# コアは dlopen で開くのでリンクしない。必要なのはヘッダだけ。
# CORE_SRC は setup_harness.sh が用意した上流ツリー（既定は ../../../../vendor/...）

REPO      := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)
CORE_SRC  ?= $(abspath $(REPO)/..)/vendor/quasi88-libretro/src

CFLAGS  += -O2 -Wall -Wextra -std=c99 -D_POSIX_C_SOURCE=200809L
CFLAGS  += -I$(CORE_SRC)/LIBRETRO/libretro-common/include
CFLAGS  += -I$(REPO)/tools/harness/core
# -MMD -MP: コンパイラにヘッダ依存を .d ファイルとして自動生成させる。
# q88h_trace.h 等 core/*.h を編集しても再ビルドされなかった事故
# （偽の測定結果が出た）の再発防止。ヘッダを手で列挙する方式は
# 列挙漏れが静かに再発するため、コンパイラの依存追跡に任せる。
CFLAGS  += -MMD -MP
LDFLAGS += -ldl

TARGET  := q88measure
DEP     := $(TARGET).d

all: $(TARGET)

$(TARGET): main.c
	@test -d "$(CORE_SRC)" || { echo "コアのソースが無い: $(CORE_SRC)"; echo "先に tools/setup_harness.sh を実行すること"; exit 1; }
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

-include $(DEP)

clean:
	rm -f $(TARGET) $(DEP)

.PHONY: all clean
