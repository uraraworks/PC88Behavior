#!/usr/bin/env python3
"""m6f-k の事前登録媒体・小文字打鍵を一元化する。"""
from __future__ import annotations
import hashlib
import json

ARMS = ('K-1', 'K-2', 'K-3', 'K-4', 'N-1', 'N-2', 'N-3', 'N-4', 'N-5', 'N-6')
MEDIA = {arm: 'KP' if arm in ('K-3', 'N-4') else 'KM' for arm in ARMS}
COMMANDS = dict(zip(ARMS, (
    'cls:kill "2:qsb"', 'cls:kill "2:qsc"', 'cls:kill "2:qsa"', 'cls:kill "2:qsu"',
    'cls:name "2:qsa" as "2:qsd"', 'cls:name "2:qsa" as "2:qsb"',
    'cls:name "2:qsc" as "2:qsd"', 'cls:name "2:qsa" as "2:qsd"',
    'cls:name "2:qsa" as "qsd"', 'cls:name "2:qsu" as "2:qsd"')))
FRAMES = {arm: 8600 for arm in ARMS}
READY_COMMAND = 'rem q6kready'


def keystrokes(arm: str) -> str:
    return COMMANDS[arm] + '\n'


def manifest() -> dict:
    entries = [{'name': 'qsa', 'units': [10], 'type': 0},
               {'name': 'qsb', 'units': [20, 21], 'type': 0},
               {'name': 'QSU', 'units': [30], 'type': 0}]
    return {'format': 'm6fk-scenario-v1', 'disk_spec': 'l3-disk-format-v5',
            'media': {'KM': entries, 'KP': entries},
            'arms': [{'id': arm, 'media': MEDIA[arm], 'command': keystrokes(arm),
                      'runs': 2, 'frames': FRAMES[arm]} for arm in ARMS],
            'ready_probe': {'command': READY_COMMAND + '\n', 'frame': 8100, 'snapshot': 8600}}


def canonical(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, ensure_ascii=True, separators=(',', ':'))+'\n').encode('ascii')


def digest(doc: dict) -> str:
    return hashlib.sha256(canonical(doc)).hexdigest()


def validate(doc: dict) -> None:
    if doc != manifest() or any(x['command'] != x['command'].lower() for x in doc['arms']):
        raise ValueError('G3')
