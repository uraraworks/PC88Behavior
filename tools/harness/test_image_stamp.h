/* 自作媒体専用: コアが選んだ像からセクタ先頭の刻印を読む。 */
#include <stdio.h>
#include <dlfcn.h>
#define QUASI88_MAX_FILENAME 1024
#include "drive.h"

static int test_image_stamp(const char *core, int unit)
{
    void *h = dlopen(core, RTLD_NOW);
    PC88_DRIVE_T *drives = h ? dlsym(h, "drive") : NULL;
    int (*seek_fn)(OSD_FILE *, long, int) = NULL;
    long (*tell_fn)(OSD_FILE *) = NULL;
    size_t (*read_fn)(void *, size_t, size_t, OSD_FILE *) = NULL;
    unsigned char stamp[4];
    if (!h || !drives) return 0;
    *(void **)(&seek_fn) = dlsym(h, "osd_fseek");
    *(void **)(&tell_fn) = dlsym(h, "osd_ftell");
    *(void **)(&read_fn) = dlsym(h, "osd_fread");
    if (!seek_fn || !tell_fn || !read_fn || !drives[unit].fp) return 0;
    OSD_FILE *fp = drives[unit].fp;
    long old = tell_fn(fp);
    if (old < 0 || seek_fn(fp, drives[unit].disk_top + 688 + 16, SEEK_SET) ||
        read_fn(stamp, 1, sizeof stamp, fp) != sizeof stamp || seek_fn(fp, old, SEEK_SET)) return 0;
    fprintf(stderr, "test-image-stamp=%02x%02x%02x%02x\n", stamp[0], stamp[1], stamp[2], stamp[3]);
    dlclose(h);
    return 1;
}
