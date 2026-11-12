#!/usr/bin/env python3
"""既存計測コアの OUT 内コピーを B88 用に構築する。元の vendor は変更しない。"""
import os
import json
import platform
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('計測フックの適用位置が一意ではありません')
    return text.replace(old, new, 1)


def build(output):
    source = Path(os.environ.get('PC88_CORE_SOURCE', ROOT.parent / 'vendor/quasi88-libretro'))
    work = output / 'build'
    shutil.copytree(source, work, ignore=shutil.ignore_patterns('.git', '*.o', '*.d', '*.so', '*.dylib', '*.dll'))
    p = work / 'src/pc88sub.c'
    s = p.read_text()
    prefix, s = s.split('#include "q88h_trace.h"', 1)
    s = replace_once(s, 'static byte q88h_sub_fetch( word addr )',
                     '#include "b88_capture.c"\n\nstatic byte q88h_sub_fetch( word addr )')
    s = replace_once(s, '  t->n_write++;\n  sub_mem_write( addr, data );', '  t->n_write++;\n  b88_write(addr, data);\n  sub_mem_write( addr, data );')
    s = replace_once(s, '  v = sub_io_in( port );', '  v = sub_io_in( port );\n  b88_port(0, port, v);')
    s = replace_once(s, '  sub_io_out( port, data );', '  b88_port(1, port, data);\n  sub_io_out( port, data );')
    p.write_text(prefix + '#include "q88h_trace.h"' + s)
    shutil.copyfile(ROOT / 'tools/b88_capture.c', work / 'src/b88_capture.c')
    p.write_text(p.read_text().replace('#include "b88_capture.c"', '#include "b88a2_capture.c"'))
    shutil.copyfile(ROOT / 'tools/b88a2_capture.c', work / 'src/b88a2_capture.c')
    p.write_text(replace_once(p.read_text(), '  v = sub_io_in( port );',
                             '  b88a2_before_in(port);\n  v = sub_io_in( port );'))
    p = work / 'src/z80.c'
    s = p.read_text()
    s = replace_once(s, '#include "pc88cpu.h"',
                     '#include "pc88cpu.h"\nextern void retro_b88_instr(int, unsigned);\nextern void retro_b88a2_interrupt(void);\nextern void retro_b88a2_ei_delay(unsigned);')
    s = replace_once(s, '      opcode = M_FETCH(z80->PC.W++);',
                     '      retro_b88_instr(z80 == &z80main_cpu, z80->PC.W);\n      opcode = M_FETCH(z80->PC.W++);')
    s = replace_once(s, '    z80->IFF = INT_DISABLE;',
                     '    if (z80 == &z80sub_cpu) retro_b88a2_interrupt();\n    z80->IFF = INT_DISABLE;')
    s = replace_once(s, '      z80->skip_intr_chk = FALSE;', '      if (z80 == &z80sub_cpu) retro_b88a2_ei_delay(z80->PC.W);\n      z80->skip_intr_chk = FALSE;')
    p.write_text(s)
    p = work / 'src/q88h_memlog.c' 
    s = p.read_text()
    s = replace_once(s, '#include "q88h_memlog.h"',
                     '#include "q88h_memlog.h"\nextern int retro_b88_main_write(unsigned, unsigned);')
    s = replace_once(s, '  if( l->n_events >= Q88H_MEMLOG_MAX_EVENTS ){',
                     '  if (!retro_b88_main_write(pc, addr)) return;\n  if( l->n_events >= Q88H_MEMLOG_MAX_EVENTS ){')
    p.write_text(s)
    with (output / 'build.log').open('w') as log:
        subprocess.run(['make', '-j2', 'platform=' + ('osx' if platform.system() == 'Darwin' else 'unix')], cwd=work, stdout=log, stderr=log, check=True)
    cores = [p for p in work.glob('quasi88_libretro.*') if p.suffix in ('.so', '.dylib', '.dll')]
    if len(cores) != 1:
        raise ValueError('計測コアを特定できません')
    core = output / cores[0].name
    shutil.copyfile(cores[0], core)
    # フレーム上限で未帰還でも観測を閉じる。既存 frontend 本体は変更しない。
    s = (ROOT / 'tools/harness/frontend/main.c').read_text()
    # OUT へ移した frontend では argv[0] の4段上はリポジトリではない。
    # 保存先の拒否判定は、コピー元リポジトリの実体パスへ固定する。
    s = replace_once(s, 'set_repo_root_from_argv0(argv[0]);',
                     'strncpy(g_repo_root, ' + json.dumps(str(ROOT)) + ', sizeof(g_repo_root)-1);')
    s = replace_once(s, 'static void (*p_deinit)(void);',
                     'static void (*p_deinit)(void);\nstatic int (*b88_finish)(void);')
    s = replace_once(s, '    SYM(p_deinit,                 "retro_deinit");',
                     '    SYM(p_deinit,                 "retro_deinit");\n    SYM(b88_finish, "retro_b88_finish");')
    pos = s.rfind('        p_unload_game();')
    if pos < 0:
        raise ValueError('frontend の終了位置がありません')
    s = s[:pos] + '''        {
            if (!b88_finish()) failed = 1;
        }
''' + s[pos:]
    front_src = output / 'b88_frontend.c'
    front_src.write_text(s)
    front = output / 'b88_frontend'
    with (output / 'build.log').open('a') as log:
        subprocess.run(['cc', '-O2', '-std=c99', '-D_POSIX_C_SOURCE=200809L',
                        '-I' + str(work / 'src/LIBRETRO/libretro-common/include'),
                        '-I' + str(ROOT / 'tools/harness/core'),
                        '-I' + str(ROOT / 'tools/harness/frontend'),
                        str(front_src), '-ldl', '-o', str(front)],
                       stdout=log, stderr=log, check=True)
    shutil.rmtree(work)
    front_src.unlink()
    return core, front
