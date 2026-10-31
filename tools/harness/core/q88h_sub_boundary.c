#include <string.h>
#include "q88h_sub_boundary.h"
static q88h_boundary_t sub;
q88h_boundary_t *retro_q88h_sub_boundary(void) { return &sub; }
void retro_q88h_sub_boundary_reset(void)
{
    memset(&sub, 0, sizeof(sub));
    sub.magic = Q88H_BOUNDARY_MAGIC;
    sub.version = Q88H_BOUNDARY_VERSION;
    sub.last_class = sub.cur_class = Q88H_BND_NONE;
}
void retro_q88h_sub_boundary_set_enabled(int enabled) { sub.enabled = !!enabled; }
