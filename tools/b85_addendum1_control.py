#!/usr/bin/env python3
"""自作同士の陰性・読み戻し・比較故障注入を検査する。"""
import sys
from pathlib import Path
from analyze_main_to_sub import parse_iolog
from analyze_b16 import io_drops
from analyze_m6ia_main_sub import read_memlog
from b85_addendum1_rom import PATTERN
from b85_addendum1_summary import prefix_matches

root = Path(sys.argv[1]) / 'raw'
for name in ('negative', 'positive'):
    io = root / f'control-{name}.io'
    assert io_drops(io) == 0
    events, masked = parse_iolog(io)
    assert not masked
    main = [e for e in events if e.cpu == 'main']
    from collections import Counter
    # 起動中にも同じ列がある場合は一度だけ現れる位置を使う。
    pairs = [(a.pc, b.pc, b.clock) for a, b in zip(main, main[1:])
             if a.kind == b.kind == 'IN' and a.port == b.port == '0040' and a.pc != b.pc]
    counts = Counter((a, b) for a, b, _ in pairs)
    markers = [c for a, b, c in pairs if counts[a, b] == 1]
    assert len(markers) == 1
    after = [e for e in events if e.clock > markers[0]]
    sent = [e.value for e in after if e.cpu == 'main' and e.kind == 'OUT' and e.port == '00FD']
    received = [e.value for e in after if e.cpu == 'main' and e.kind == 'IN' and e.port == '00FC']
    sub = [e.value for e in after if e.cpu == 'sub' and e.kind == 'OUT' and e.port == '00FD']
    mem = {e.addr: e.value for e in read_memlog(root / f'control-{name}.mem')}
    assert mem.get(0xdf52) == 3 and mem.get(0xdf53) == 1
    assert received == sub
    if name == 'negative':
        assert sent == [] and received == []
    else:
        assert sent == [0x15, 0x78, 0, 0, 16] and len(received) == len(PATTERN)
        assert prefix_matches(received, PATTERN)
        altered = bytearray(PATTERN); altered[0] ^= 1
        assert not prefix_matches(received, altered)
print('陰性・読み戻し・比較故障注入 PASS')
