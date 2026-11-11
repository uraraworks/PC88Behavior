#define main q88measure_main
#include "frontend/main.c"
#undef main
#include <assert.h>
int main(void) {
    struct retro_variable v = {"q88_sound_board", NULL};
    assert(!environment_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &v) && !v.value);
    g_sound_board = "OPN";
    assert(environment_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &v) && !strcmp(v.value,"OPN"));
    g_sound_board = "OPNA";
    assert(environment_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &v) && !strcmp(v.value,"OPNA"));
    return 0;
}
