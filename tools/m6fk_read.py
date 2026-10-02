#!/usr/bin/env python3
"""m6f-k: 配置済み3枠とFAT0〜159のみ値を扱い、他は変化の真偽だけ。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from m6fh_body import BodyError, Image
import m6fk_script as script

PLACED = (0, 1, 2)


def inspect(data: bytes, arm: str) -> dict:
    if arm not in script.ARMS:
        raise ValueError('腕ID')
    image = Image(data)
    entries = [dict(position=i, fields=list(image.sector_prefix((18, 1, 1), 48)[i*16:(i+1)*16]))
               for i in PLACED]
    fats = [bytes(image.sector_prefix((18, 1, r), 160)) for r in (14, 15, 16)]
    if len(set(fats)) != 1:
        raise BodyError('割り当て表の複製')
    return dict(entries=entries, fat_0_159=list(fats[0]), g8_max_position=159)


def units(snapshot: dict, slot: int) -> list[int]:
    unit = snapshot['entries'][slot]['fields'][10]
    result = []
    while unit < 160 and unit not in result and unit not in (74, 75):
        result.append(unit)
        value = snapshot['fat_0_159'][unit]
        if 0xc0 <= value <= 0xc8:
            return result
        unit = value
    raise BodyError('鎖')


def compare(before_data: bytes, after_data: bytes, arm: str) -> tuple[dict, dict, dict]:
    before, after = inspect(before_data, arm), inspect(after_data, arm)
    a, b = Image(before_data), Image(after_data)
    if a.sectors.keys() != b.sectors.keys():
        raise BodyError('セクタ構造変化')
    slots = []
    renamed_slots = []  # 内部照合のみ。安全な出力には含めない。
    for slot in range(3, 192):
        coord = (18, 1, slot//16+1)
        start = (slot%16)*16
        # 等否のみ。値・名前・署名を結果にも例外にも持ち出さない。
        changed = a.sector(*coord)[start:start+16] != b.sector(*coord)[start:start+16]
        slots.append(dict(position=slot, changed=changed))
        if changed and b.sector(*coord)[start:start+9] == b"qsd".ljust(9, b" "):
            renamed_slots.append(slot)
    sectors = []
    marker = []
    for coord in sorted(a.sectors):
        if coord[0:2] == (18, 1):
            if coord[2] == 13:
                marker.append(dict(position=list(coord), changed=a.sector(*coord) != b.sector(*coord)))
            continue  # FAT160以降を比較しない。
        sectors.append(dict(position=list(coord), changed=a.sector(*coord) != b.sector(*coord)))
    delta = [dict(position=i, before=x, after=y) for i, (x, y) in
             enumerate(zip(before['fat_0_159'], after['fat_0_159'])) if x != y]
    changes = dict(unplaced_slots=slots, body_sectors=sectors, marker_sectors=marker,
                   fat_changes=delta, structure_changed=before_data[:688] != after_data[:688])
    changes['structure_changed'] |= any(
        before_data[start-16:start] != after_data[b.sectors[coord][0]-16:b.sectors[coord][0]]
        for coord, (start, _) in a.sectors.items())
    changes['_renamed_slots'] = renamed_slots
    changes['media_unchanged'] = (before == after and not changes['structure_changed'] and
                                 not any(x['changed'] for x in slots+sectors+marker))
    return before, after, changes


def _masked(before: dict, after: dict) -> tuple[list, list]:
    # 11〜15バイト目は意味が未確定なので値を出さず、変化の真偽だけを出す。
    out_b, out_a = [], []
    for b, a in zip(before['entries'], after['entries']):
        out_b.append(dict(position=b['position'], fields=b['fields'][:11]))
        out_a.append(dict(position=a['position'], fields=a['fields'][:11],
                          tail_11_15_changed=a['fields'][11:16] != b['fields'][11:16]))
    return out_b, out_a


def safe_result(before: dict, after: dict, changes: dict) -> dict:
    entries_before, entries_after = _masked(before, after)
    return dict(entries_before=entries_before, entries_after=entries_after,
                g8_max_position=after['g8_max_position'],
                **{k: v for k, v in changes.items() if not k.startswith('_')})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True, type=Path)
    ap.add_argument('--before', required=True, type=Path)
    ap.add_argument('--arm', required=True, choices=script.ARMS)
    args = ap.parse_args()
    try:
        print(json.dumps(safe_result(*compare(args.before.read_bytes(), args.image.read_bytes(), args.arm)),
                         sort_keys=True, separators=(',', ':')))
        return 0
    except (OSError, ValueError, BodyError):
        print('{"gate":"NG","reason":"read"}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
