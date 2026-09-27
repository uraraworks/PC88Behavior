#!/usr/bin/env python3
"""check_m6ff_preregistration.py — m6f-f の凍結表 tools/m6ff_frozen.tsv を、
tools/m6ff_keystrokes.py（打鍵の唯一の真実の源）と現物の生成器から
再計算した値と照合する。tools/measure_m6ff.sh は、腕を1本でも走らせる
前・公式ROMを起動する前に、必ずこの照合をrc=0で通す（事前登録第5節 G3）。

media_sha256 は、その場で B0 と同じ規則の媒体を再生成してハッシュし直す
（コミットした媒体ファイルを持たない設計なので、比較対象は常に再生成)。
keystroke_sha256 は、凍結表自身が持つ bsave_addr を使って
tools/m6ff_keystrokes.keystrokes() を再実行し、その場でハッシュし直す。
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import m6ff_keystrokes as k  # noqa: E402
import make_m6ff_frozen as mkf  # noqa: E402


class GateError(ValueError):
    pass


def load_tsv(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("\t")
        if not sep or not key:
            raise GateError("凍結表の形式")
        out.setdefault(key, []).append(value)
    return out


def one(cfg: dict[str, list[str]], key: str) -> str:
    values = cfg.get(key, [])
    if len(values) != 1:
        raise GateError(f"{key}が一意でない")
    return values[0]


def parse_keyed(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        key, sep, rest = value.partition(":")
        if not sep or key in out:
            raise GateError("キー付き凍結値の形式")
        out[key] = rest
    return out


def check(cfg: dict[str, list[str]]) -> str:
    expected_keys = (set(mkf.SINGLETONS) | {"bsave_addr", "media_sha256",
                      "arm", "keystroke_sha256", "judgment"})
    if set(cfg) != expected_keys:
        raise GateError("設定キーに不足または余分")

    for key, value in mkf.SINGLETONS.items():
        if one(cfg, key) != value:
            raise GateError(f"凍結値不一致: {key}")

    if tuple(cfg["arm"]) != tuple(k.ARMS):
        raise GateError("腕名または順序")
    if tuple(cfg["judgment"]) != tuple(mkf.JUDGMENTS):
        raise GateError("判定名")

    addr_raw = one(cfg, "bsave_addr")
    try:
        addr = int(addr_raw, 10)
    except ValueError:
        raise GateError("bsave_addrの表記(10進で保存する約束)") from None
    try:
        k._validate_addr(addr)  # noqa: SLF001 (凍結表専用の再検証)
    except k.KeystrokeError as exc:
        raise GateError(str(exc)) from None

    recomputed_media = mkf.media_sha256()
    if one(cfg, "media_sha256") != recomputed_media:
        raise GateError("media_sha256不一致")

    keyed = parse_keyed(cfg["keystroke_sha256"])
    if set(keyed) != set(k.ARMS):
        raise GateError("keystroke_sha256の腕集合")
    for arm in k.ARMS:
        text = k.keystrokes(arm, addr if arm == "F-B" else None)
        digest = hashlib.sha256(text.encode("ascii")).hexdigest()
        if keyed[arm] != digest:
            raise GateError(f"keystroke_sha256不一致: {arm}")

    return hashlib.sha256(b"\n".join(
        f"{key}\t{v}".encode("utf-8") for key in sorted(cfg) for v in cfg[key]
    )).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6ff_frozen.tsv")
    args = ap.parse_args()
    try:
        cfg = load_tsv(args.config)
        digest = check(cfg)
    except (OSError, UnicodeError, ValueError, GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    print(f"m6f-f preregistration gate: OK sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
