#!/usr/bin/env python3
"""差分媒体の実関数を合成入出力で検査する。ROM・媒体は使用しない。

使い方: python3 tools/harness/diff_file_selftest.py --work-dir DIR [--source FILE]
AddressSanitizer と全要素比較で、先頭・末尾・短い読み取り・空差分を検査する。
"""
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[3] /
                        'vendor/quasi88-libretro/src/LIBRETRO/file-op.c')
    args = parser.parse_args()
    source = args.source.read_text()
    functions = source[source.index('size_t osd_fread_diff('):source.index('#define SAVE_DIFF')]
    args.work_dir.mkdir(parents=True, exist_ok=True)
    cfile = args.work_dir / 'diff-file.c'
    binary = args.work_dir / 'diff-file'
    cfile.write_text(r'''
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
typedef struct { void *fp, *sfp, *mem_file; } OSD_FILE;
static int base, delta;
static size_t base_count, delta_count;
static unsigned char saved[256];
static long filestream_tell(void *p) { return 0; }
static int filestream_seek(void *p, long n, int w) { return 0; }
static size_t filestream_read(void *p, void *b, size_t n) {
    size_t count = p == &base ? base_count : delta_count;
    if (count > n) count = n;
    memset(b, p == &base ? 10 : 1, count);
    return count;
}
static size_t filestream_write(void *p, const void *b, size_t n) {
    memcpy(saved, b, n); return n;
}
''' + functions + r'''
int main(int argc, char **argv) {
    OSD_FILE stream = {&base, &delta, NULL};
    const size_t sizes[] = {0, 1, 16, 256};
    for (size_t k = 0; k < 4; ++k) {
        size_t n = sizes[k];
        for (size_t count = 0; count <= n; ++count) {
            unsigned char *buf = malloc(n);
            memset(buf, 11, n);
            if (argc > 1) {
                base_count = count;
                assert(osd_fwrite_diff(buf, n, &stream) == n);
                for (size_t i = 0; i < n; ++i)
                    assert(saved[i] == (i < count ? 1 : 0));
            } else {
                base_count = n; delta_count = count;
                assert(osd_fread_diff(buf, n, &stream) == n);
                for (size_t i = 0; i < n; ++i)
                    assert(buf[i] == (i < count ? 11 : 10));
            }
            free(buf);
        }
    }
    puts("PASS: 合成差分の全要素・境界・短い読み取り・空差分");
    return 0;
}
''')
    subprocess.run(['cc', '-fsanitize=address', '-g', '-O1', str(cfile), '-o', str(binary)], check=True)
    subprocess.run([str(binary.resolve())], check=True)
    subprocess.run([str(binary.resolve()), 'write'], check=True)


if __name__ == '__main__':
    main()
