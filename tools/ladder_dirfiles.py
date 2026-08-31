#!/usr/bin/env python3
"""自作ファイル本数ラダー用の安全な集計・到達判定器。

生の画面本文とI/O値列は入力内部でだけ扱い、標準出力へは件数、位置、
SHA-256、自分で打鍵した文字列、自作マーカー、自作名、公開FDCコマンド名
だけをJSONで出す。公式ROM/ディスクのファイル自体は開かない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_write_path as awp  # noqa: E402


class LadderError(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":")).encode("ascii")


def screen_rows(path: Path) -> list[str]:
    rows: list[str] = []
    on = False
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as ex:
        raise LadderError("画面報告を読めない") from ex
    for line in lines:
        if line == "[測定終了時のテキスト画面]":
            on = True
            continue
        if not on:
            continue
        if not line.strip():
            break
        m = re.match(r"^\s+(\d+)\|\s?(.*)$", line)
        if m:
            rows.append(m.group(2).strip())
    if not on:
        raise LadderError("画面報告にテキスト画面節が無い")
    return rows


def next_exact(rows: list[str], wanted: str, start: int = 0) -> int | None:
    wanted = wanted.lower()
    return next((i for i in range(start, len(rows))
                 if rows[i].strip().lower() == wanted), None)


def typed_reflected(rows: list[str], typed: list[str]) -> bool:
    lowered = [row.strip().lower() for row in rows]
    cursor = 0
    for item in typed:
        item_l = item.strip().lower()
        pos = next((i for i in range(cursor, len(lowered))
                    if item_l in lowered[i]), None)
        if pos is None:
            return False
        cursor = pos + 1
    return True


def marker_then_ok(rows: list[str], marker: str) -> bool:
    pos = next_exact(rows, marker)
    if pos is None:
        return False
    return next_exact(rows, "ok", pos + 1) is not None


def create_screen_classification(rows: list[str], marker: str | None) -> tuple[str, bool]:
    """本文を見ず、RUN後のマーカー／非空行／Okの位置だけで分類する。"""
    run = next_exact(rows, "run")
    marker_pos = next_exact(rows, marker) if marker else None
    if run is not None and marker_pos is not None:
        ok = next_exact(rows, "ok", marker_pos + 1)
        if ok is not None:
            return "normal_success", False
    if run is None:
        return "run_not_reflected", False
    ok = next_exact(rows, "ok", run + 1)
    if marker_pos is None and ok is not None:
        # write_screenは空行を出さない。RUNとOkの間に1行以上あれば、
        # 本文を照合せず「正常マーカーでない表示を挟んでOkへ復帰」と言える。
        if ok > run + 1:
            return "error_display", ok == run + 2
        return "marker_missing_direct_ok", False
    return "incomplete", False


def reach(kind: str, rows: list[str], typed: list[str], marker: str | None) -> bool:
    low = [r.strip().lower() for r in rows]
    if kind == "missing":
        if not typed_reflected(rows, typed):
            return False
        run = next_exact(rows, "run")
        d9e = next_exact(rows, "d9e", 0 if run is None else run + 1)
        d9c = next_exact(rows, "d9c", 0 if d9e is None else d9e + 1)
        ok = next_exact(rows, "ok", 0 if d9c is None else d9c + 1)
        return (run is not None and d9e is not None and d9c is not None
                and ok is not None and "d9n" not in low)
    if kind in {"create", "verify"}:
        return bool(marker and typed_reflected(rows, typed)
                    and marker_then_ok(rows, marker))
    if kind == "files":
        # m7dz補遺どおり、FILES打鍵行の最終画面残存は要求しない。
        return next_exact(rows, "ok") is not None
    raise LadderError(f"未知のrun種別: {kind}")


def dropped_counts(path: Path) -> tuple[int, int]:
    cpu: str | None = None
    found: dict[str, int] = {}
    pat = re.compile(r"^# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件$")
    try:
        fp = path.open(encoding="utf-8", errors="strict")
    except OSError as ex:
        raise LadderError("I/Oログを読めない") from ex
    with fp:
        for raw in fp:
            s = raw.strip()
            if s == "# main":
                cpu = "main"
            elif s == "# sub":
                cpu = "sub"
            else:
                m = pat.match(s)
                if m and cpu:
                    found[cpu] = int(m.group(1))
    if set(found) != {"main", "sub"}:
        raise LadderError("main/subの取りこぼしヘッダが揃っていない")
    return found["main"], found["sub"]


def event_key(e: m2s.Ev, with_value: bool = True) -> tuple[Any, ...]:
    base = (e.cpu, e.seq, e.clock, e.frame, e.kind, e.port, e.pc)
    return base + ((e.value,) if with_value else ())


def value_sha(events: list[m2s.Ev]) -> str:
    if any(e.value is None for e in events):
        raise LadderError("値SHAの対象に伏せ字イベントがある")
    return sha(bytes(int(e.value) for e in events))


def analyze(report: Path, iolog: Path, kind: str, typed: list[str],
            marker: str | None) -> dict[str, Any]:
    rows = screen_rows(report)
    main_drop, sub_drop = dropped_counts(iolog)
    try:
        events, masked = m2s.parse_iolog(iolog)
        if sum(masked.values()):
            raise LadderError("生ログであるべき入力に伏せ字値がある")
        commands = awp.parse_commands(events)
    except (OSError, ValueError, awp.SafeError) as ex:
        # awp.SafeErrorには未知のデータポート値が含まれ得るので転記しない。
        raise LadderError("I/Oログ解析不能") from ex
    if not events:
        raise LadderError("I/Oイベントが0件")

    names = [awp.NAMES[c.opcode] for c in commands]
    entry_events = [e for e in events if e.frame >= 700]
    entry_cmds = [c for c in commands if c.frame >= 700]
    entry_names = [awp.NAMES[c.opcode] for c in entry_cmds]
    main_fc = [e for e in events if e.cpu == "main" and e.kind == "IN"
               and e.port == "00FC"]
    main_fd = [e for e in events if e.cpu == "main" and e.kind == "IN"
               and e.port == "00FD"]
    entry_fc = [e for e in main_fc if e.frame >= 700]
    entry_fd = [e for e in main_fd if e.frame >= 700]
    reads = names.count("READ DATA")
    seeks = names.count("SEEK")
    writes = sum(names.count(n) for n in
                 ("WRITE DATA", "WRITE DELETED DATA", "FORMAT TRACK"))
    entry_reads = entry_names.count("READ DATA")
    entry_writes = sum(entry_names.count(n) for n in
                       ("WRITE DATA", "WRITE DELETED DATA", "FORMAT TRACK"))
    reached = reach(kind, rows, typed, marker)
    screen_class, ok_after_error = (
        create_screen_classification(rows, marker)
        if kind == "create" else ("not_applicable", False)
    )

    accepted = reached and main_drop == 0 and sub_drop == 0
    if kind == "missing":
        accepted = accepted and (len(entry_fc) > 0 or entry_reads > 0) and writes == 0
    elif kind == "create":
        accepted = accepted and writes > 0
    elif kind == "verify":
        accepted = accepted and writes == 0
    elif kind == "files":
        accepted = accepted and reads > 0 and writes == 0

    screen_blob = "\n".join(rows) + ("\n" if rows else "")
    result: dict[str, Any] = {
        "schema": 1,
        "kind": kind,
        "accepted": accepted,
        "reach": reached,
        "typed": typed,
        "marker": marker,
        "screen_classification": screen_class,
        "ok_after_error": ok_after_error,
        "screen_lines": len(rows),
        "screen_chars": sum(len(r) for r in rows),
        "screen_sha256": sha(screen_blob.encode("utf-8")),
        "main_dropped": main_drop,
        "sub_dropped": sub_drop,
        "event_count": len(events),
        "event_sha256": sha(json_bytes([event_key(e) for e in events])),
        "entry_shape_count": len(entry_events),
        "entry_shape_sha256": sha(json_bytes(
            [(e.cpu, e.kind, e.port, e.pc) for e in entry_events])),
        "main_in_fc": len(main_fc),
        "main_in_fc_sha256": value_sha(main_fc),
        "main_in_fd": len(main_fd),
        "main_in_fd_sha256": value_sha(main_fd),
        "entry_main_in_fc": len(entry_fc),
        "entry_main_in_fc_sha256": value_sha(entry_fc),
        "entry_main_in_fd": len(entry_fd),
        "entry_main_in_fd_sha256": value_sha(entry_fd),
        "fdc_count": len(names),
        "fdc_names": names,
        "fdc_sha256": sha(json_bytes(names)),
        "read_count": reads,
        "seek_count": seeks,
        "write_count": writes,
        "entry_fdc_count": len(entry_names),
        "entry_fdc_names": entry_names,
        "entry_fdc_sha256": sha(json_bytes(entry_names)),
        "entry_read_count": entry_reads,
        "entry_seek_count": entry_names.count("SEEK"),
        "entry_write_count": entry_writes,
        "entry_first_frame": min((e.frame for e in entry_events), default=None),
        "entry_first_clock": min((e.clock for e in entry_events), default=None),
    }
    return result


PAIR_FIELDS = (
    "accepted", "reach", "screen_lines", "screen_chars", "screen_sha256",
    "main_dropped", "sub_dropped", "event_count", "event_sha256",
    "entry_shape_count", "entry_shape_sha256", "main_in_fc",
    "main_in_fc_sha256", "main_in_fd", "main_in_fd_sha256",
    "entry_main_in_fc", "entry_main_in_fc_sha256", "entry_main_in_fd",
    "entry_main_in_fd_sha256", "fdc_count", "fdc_names", "fdc_sha256",
    "read_count", "seek_count", "write_count", "entry_fdc_count",
    "entry_fdc_names", "entry_fdc_sha256", "entry_read_count",
    "entry_seek_count", "entry_write_count",
)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as ex:
        raise LadderError("安全集計JSONを読めない") from ex
    if not isinstance(value, dict):
        raise LadderError("安全集計JSONがobjectでない")
    return value


def pair(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    mismatches = [key for key in PAIR_FIELDS if a.get(key) != b.get(key)]
    out = dict(a)
    out["pair_match"] = not mismatches
    out["pair_mismatches"] = mismatches
    out["accepted"] = bool(a.get("accepted") and b.get("accepted") and not mismatches)
    return out


def media_sha(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fp:
            while chunk := fp.read(1024 * 1024):
                h.update(chunk)
    except OSError as ex:
        raise LadderError("チェックポイントを読めない") from ex
    return h.hexdigest()


def manifest_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    try:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("objectでない")
            out.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as ex:
        raise LadderError(f"manifestが不正: {ex}") from ex
    return out


def manifest_add(path: Path, record: dict[str, Any]) -> None:
    records = manifest_records(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            for old in records:
                fp.write(json.dumps(old, ensure_ascii=False, sort_keys=True) + "\n")
            fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def latest(records: list[dict[str, Any]], stage: str, n: int) -> dict[str, Any] | None:
    hits = [r for r in records if r.get("stage") == stage and r.get("n") == n]
    return hits[-1] if hits else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyze")
    an.add_argument("--report", required=True, type=Path)
    an.add_argument("--iolog", required=True, type=Path)
    an.add_argument("--kind", required=True,
                    choices=("missing", "create", "verify", "files"))
    an.add_argument("--typed", action="append", default=[])
    an.add_argument("--marker")
    an.add_argument("--out", type=Path)
    pa = sub.add_parser("pair")
    pa.add_argument("--a", required=True, type=Path)
    pa.add_argument("--b", required=True, type=Path)
    pa.add_argument("--out", type=Path)
    ms = sub.add_parser("media-sha")
    ms.add_argument("path", type=Path)
    ma = sub.add_parser("manifest-add")
    ma.add_argument("--manifest", required=True, type=Path)
    ma.add_argument("--record", required=True, type=Path)
    st = sub.add_parser("status")
    st.add_argument("--manifest", required=True, type=Path)
    st.add_argument("--stage", required=True)
    st.add_argument("--n", required=True, type=int)
    st.add_argument("--disk", type=Path)
    args = ap.parse_args()
    try:
        if args.cmd == "analyze":
            result = analyze(args.report, args.iolog, args.kind, args.typed, args.marker)
            text = json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
            if args.out:
                args.out.write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
            return 0 if result["accepted"] else 1
        if args.cmd == "pair":
            result = pair(read_json(args.a), read_json(args.b))
            text = json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
            if args.out:
                args.out.write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
            return 0 if result["accepted"] else 1
        if args.cmd == "media-sha":
            print(media_sha(args.path))
            return 0
        if args.cmd == "manifest-add":
            manifest_add(args.manifest, read_json(args.record))
            return 0
        if args.cmd == "status":
            record = latest(manifest_records(args.manifest), args.stage, args.n)
            if not record or not record.get("accepted"):
                return 1
            if args.disk and record.get("media_sha256") != media_sha(args.disk):
                return 1
            return 0
    except LadderError as ex:
        print(f"不合格: {ex}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
