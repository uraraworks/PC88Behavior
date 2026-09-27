#!/usr/bin/env python3
"""make_m6ff_frozen.py — m6f-f の凍結表 tools/m6ff_frozen.tsv を作る。

事前登録 docs/notes/m6f-f-type-byte-by-save-mode-preregistration.md 第5節
G3「凍結値（媒体・打鍵列のSHA-256）」を、実際に生成した値から機械的に
作る道具。番地（--bsave-addr）はマニュアルの言語仕様から親が決める値を
そのまま渡す（このスクリプト自身はマニュアルを読まない。追補1参照）。

打鍵テキストは tools/m6ff_keystrokes.py が唯一の真実の源。ここでは
そのSHA-256を計算するだけで、テキストを別途書き写さない。

媒体のSHA-256は、ドライブ2に使う空の媒体（tools/make_m6fc_blank_disk.py の
B0と同じ規則: --fat-value 0xFF --filler 0xFF --sector-fill 18,1,13=0x00）を
一時ファイルへ生成し、その場でハッシュしてから削除して求める（媒体そのもの
はリポジトリへコミットしない）。

出力はTSV（key\\tvalue、arm/judgmentのように複数行になりうるキーは複数行）。
既存ファイルは --force を付けない限り上書きしない。
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import m6ff_keystrokes as k  # noqa: E402

JUDGMENTS = (
    "gate_failed",
    "type_byte",
    "inconclusive",
    "no_entry",
    "bytes11_15_unchanged",
    "bytes11_15_vary",
    "control_failed",
)

SINGLETONS = {
    "frozen": "yes",
    "repetitions": "2",
    "run_timeout_seconds": "300",
    "boot_return_frame": str(k.BOOT_FRAME),
    "stimulus_frame": str(k.STIMULUS_FRAME),
    "run_frames": str(k.RUN_FRAMES),
    "reference_disk": "N88_FE.D88",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def media_sha256() -> str:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "b0.d88"
        subprocess.run(
            [sys.executable, str(HERE / "make_m6fc_blank_disk.py"), str(out),
             "--fat-value", "0xFF", "--filler", "0xFF",
             "--sector-fill", "18,1,13=0x00"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return _sha256_bytes(out.read_bytes())


def build_lines(bsave_addr: int) -> list[str]:
    lines: list[str] = []
    for key, value in SINGLETONS.items():
        lines.append(f"{key}\t{value}")
    lines.append(f"bsave_addr\t{bsave_addr}")
    lines.append(f"media_sha256\t{media_sha256()}")
    for arm in k.ARMS:
        lines.append(f"arm\t{arm}")
    for arm in k.ARMS:
        addr = bsave_addr if arm == "F-B" else None
        text = k.keystrokes(arm, addr)
        digest = _sha256_bytes(text.encode("ascii"))
        lines.append(f"keystroke_sha256\t{arm}:{digest}")
    for name in JUDGMENTS:
        lines.append(f"judgment\t{name}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bsave-addr", required=True,
                     help="F-Bで使う番地。10進、または &H 接頭辞つき16進(例: &HD000)")
    ap.add_argument("--out", type=Path, default=HERE / "m6ff_frozen.tsv")
    ap.add_argument("--force", action="store_true", help="既存の出力を上書きする")
    args = ap.parse_args()
    try:
        addr = k.parse_addr(args.bsave_addr)
        lines = build_lines(addr)
    except (k.KeystrokeError, subprocess.CalledProcessError, OSError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    if args.out.exists() and not args.force:
        print(f"エラー: 既に存在する({args.out})。--forceで上書き", file=sys.stderr)
        return 1
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} (bsave_addr={addr}=0x{addr:04X})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
