#!/usr/bin/env python3
"""m6i-hのG3/G9を事前登録、m6i-g凍結値、実装と相互照合する。"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import check_m6ig_preregistration as base  # noqa: E402
import build_m6ih_measure_rom as build  # noqa: E402
import analyze_m6ih as analyzer  # noqa: E402
import judge_m6ih as judge  # noqa: E402

ARMS = ("H-N", "H-W", "H-A", "H-B")
ISSUE_FRAMES = {"H-N": 6, "H-W": 60}
EXPECTED_STATES = {
    "H-N": (0, 0, 0), "H-W": (1, 1, 0),
    "H-A": (None, 1, 0), "H-B": (None, 0, 0),
}
RETRY_MARKER_ADDRESS = 0xE00D
RESULT_CONDITIONS = {"H-N": "standard", "H-W": "standard",
                     "H-A": "standard", "H-B": "retry"}


def parse_state(value: str):
    return tuple(None if item == "*" else int(item) for item in value.split(","))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6ih_frozen.tsv")
    ap.add_argument("--prereg", type=Path,
                    default=REPO / "docs/notes/m6i-h-drop-the-fixed-wait-preregistration.md")
    ap.add_argument("--m6ig-config", type=Path, default=HERE / "m6ig_frozen.tsv")
    args = ap.parse_args()
    try:
        cfg = base.load_tsv(args.config)
        old = base.load_tsv(args.m6ig_config)
        singleton = {"frozen", "arm_frames", "repetitions", "timeout_limit",
                     "normal_media_sha256", "sector1_sha256", "plain_subrom_sha256",
                     "retry_marker_address"}
        repeated = {"arm", "issue_frame", "expected_state", "retry_required",
                    "result_condition", "judgment"}
        if set(cfg) != singleton | repeated:
            raise base.GateError("設定キーに不足または余分がある")
        for key in ("frozen", "arm_frames", "repetitions", "timeout_limit",
                    "normal_media_sha256", "sector1_sha256", "plain_subrom_sha256"):
            if base.one(cfg, key) != base.one(old, key):
                raise base.GateError(f"G3不一致: {key}")
        if int(base.one(cfg, "retry_marker_address"), 0) != RETRY_MARKER_ADDRESS:
            raise base.GateError("G9不一致: 再試行マーカー番地")

        sys.path.insert(0, str(REPO))
        import src.l3_service.make_subrom as subrom
        plain, _used = subrom.build()
        if hashlib.sha256(bytes(plain)).hexdigest() != base.one(cfg, "plain_subrom_sha256"):
            raise base.GateError("G9不一致: 素のsub ROM生成物")

        frames = base.keyed(cfg, "issue_frame", int)
        states = base.keyed(cfg, "expected_state", parse_state)
        conditions = base.keyed(cfg, "result_condition", str)
        retries = base.keyed(cfg, "retry_required", int)
        if tuple(cfg.get("arm", ())) != ARMS or tuple(build.ARMS) != ARMS \
                or tuple(analyzer.ARMS) != ARMS or tuple(judge.ARMS) != ARMS:
            raise base.GateError("G9不一致: 腕一覧")
        if frames != ISSUE_FRAMES or analyzer.ISSUE_FRAMES != ISSUE_FRAMES:
            raise base.GateError("G9不一致: 発行フレーム")
        if states != EXPECTED_STATES or analyzer.EXPECTED_STATES != EXPECTED_STATES:
            raise base.GateError("G9不一致: 到達状態")
        if retries != {"H-B": 1} or analyzer.RETRY_MARKER_ADDRESS != RETRY_MARKER_ADDRESS:
            raise base.GateError("G9不一致: 再試行条件")
        if conditions != RESULT_CONDITIONS or analyzer.RESULT_CONDITIONS != RESULT_CONDITIONS:
            raise base.GateError("G9不一致: 結果条件")
        if len(cfg["judgment"]) != len(set(cfg["judgment"])) \
                or set(cfg["judgment"]) != set(judge.REGISTERED):
            raise base.GateError("G9不一致: 判定名一覧")

        prereg = args.prereg.read_text(encoding="utf-8")
        section = prereg.split("## 4. 判定名", 1)[1].split("## 5.", 1)[0]
        documented = set(re.findall(r"`([a-z][a-z0-9_]+)`", section))
        if set(judge.REGISTERED) - documented:
            raise base.GateError("G9不一致: 文書の判定名一覧")
        required_text = ("H-A の発行フレームを凍結しない", "H-A・H-B の `a`",
                         "要求 run の件数は記録するが条件にしない")
        if any(text not in prereg for text in required_text):
            raise base.GateError("G9不一致: 非凍結条件またはH-B結果条件")
    except (OSError, UnicodeError, ValueError, IndexError, base.GateError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    print("G3/G9 preregistration gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
