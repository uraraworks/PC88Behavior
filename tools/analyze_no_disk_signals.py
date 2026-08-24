#!/usr/bin/env python3
"""no_disk と正常な B: 媒体を、自作 sub から見える信号だけで比較する。

生 iolog は内部で読むが、出力にはポート値、FDC 結果値、値の列を出さない。
公開ステータス/MSR は、各ビットについて両条件で観測された 0/1 の集合が
同じかだけを「差あり／差なし」で報告する。件数・完了・所要 clock 集合は
時間的な外形として別に報告する。
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_write_path as awp  # noqa: E402


ST0_BITS = (
    (7, "IC1"), (6, "IC0"), (5, "SEEK END"),
    (4, "EQUIPMENT CHECK"), (3, "NOT READY"),
    (2, "HEAD ADDRESS"), (1, "UNIT SELECT 1"), (0, "UNIT SELECT 0"),
)
ST1_BITS = (
    (7, "END OF CYLINDER"), (5, "DATA ERROR"), (4, "OVERRUN"),
    (2, "NO DATA"), (1, "NOT WRITABLE"), (0, "MISSING ADDRESS MARK"),
)
ST2_BITS = (
    (6, "CONTROL MARK"), (5, "DATA ERROR IN DATA FIELD"),
    (4, "WRONG CYLINDER"), (3, "SCAN EQUAL HIT"),
    (2, "SCAN NOT SATISFIED"), (1, "BAD CYLINDER"),
    (0, "MISSING ADDRESS MARK IN DATA FIELD"),
)
ST3_BITS = (
    (7, "FAULT"), (6, "WRITE PROTECTED"), (5, "READY"),
    (4, "TRACK 0"), (3, "TWO SIDE"), (2, "HEAD ADDRESS"),
    (1, "UNIT SELECT 1"), (0, "UNIT SELECT 0"),
)
MSR_BITS = (
    (7, "RQM"), (6, "DIO"), (5, "NON-DMA MODE"), (4, "FDC BUSY"),
    (3, "DRIVE 3 BUSY"), (2, "DRIVE 2 BUSY"),
    (1, "DRIVE 1 BUSY"), (0, "DRIVE 0 BUSY"),
)


class AnalysisError(ValueError):
    pass


ROM_CONFIG_LABELS = {
    "official_full": "公式ROM一式",
    "mixed_default": "混成既定（公式main一式＋自作sub既定版）",
    "mixed_intervention": "混成介入（公式main一式＋自作sub待ち介入版）",
}
EXPECTED_RUNS = {
    "mixed_no_disk": ("mixed_default", "no_disk"),
    "mixed_normal": ("mixed_default", "normal_drive2"),
    "official_no_disk": ("official_full", "no_disk"),
    "mixed_intervention": ("mixed_intervention", "no_disk"),
}


def load_run_metadata(path: Path, role: str) -> dict[str, str]:
    """runの自己申告と、報告上の役割に必要なROM構成・条件を照合する。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"{path}: runメタデータを読めない: {exc}") from exc
    if not isinstance(raw, dict):
        raise AnalysisError(f"{path}: runメタデータがobjectでない")
    required = ("schema", "run_id", "report_role", "rom_configuration", "condition")
    missing = [key for key in required if not isinstance(raw.get(key), str) or not raw[key]]
    if missing:
        raise AnalysisError(f"{path}: runメタデータ必須項目が無い: {', '.join(missing)}")
    if raw["schema"] != "pc88-no-disk-run-v1":
        raise AnalysisError(f"{path}: 未対応のrunメタデータschema")
    expected_config, expected_condition = EXPECTED_RUNS[role]
    actual = (raw["report_role"], raw["rom_configuration"], raw["condition"])
    expected = (role, expected_config, expected_condition)
    if actual != expected:
        raise AnalysisError(
            f"{path}: ラベルとROM構成/条件の不一致: "
            f"役割={actual[0]}, ROM構成={actual[1]}, 条件={actual[2]} / "
            f"期待={expected[0]}, {expected[1]}, {expected[2]}"
        )
    if raw["rom_configuration"] not in ROM_CONFIG_LABELS:
        raise AnalysisError(f"{path}: 未知のROM構成")
    return {key: str(value) for key, value in raw.items() if isinstance(value, str)}


def run_ref(meta: dict[str, str]) -> str:
    return f"{meta['run_id']}［ROM構成: {ROM_CONFIG_LABELS[meta['rom_configuration']]}］"


def comparison_ref(left: dict[str, str], right: dict[str, str]) -> str:
    return f"参照run: {run_ref(left)} 対 {run_ref(right)}"


DROP_RE = re.compile(r"^# 取りこぼし:\s*(\d+)件")
FRAMES_RE = re.compile(r"^frames\s*:\s*(\d+)\s*$")
FROM_FRAME_RE = re.compile(r"^io-log-from-frame:\s*(\d+)\s*$")


def dropped_events(path: Path) -> int:
    total = 0
    with m2s.cmp_io._open_iolog(str(path)) as fp:
        for line in fp:
            match = DROP_RE.match(line)
            if match:
                total += int(match.group(1))
    return total


def require_capture_window(path: Path, after_frame: int, through_frame: int) -> None:
    """必要区間全体がI/O記録対象だったことをログの測定条件から保証する。"""
    frames = from_frame = None
    with m2s.cmp_io._open_iolog(str(path)) as fp:
        for line in fp:
            match = FRAMES_RE.match(line)
            if match:
                frames = int(match.group(1))
            match = FROM_FRAME_RE.match(line)
            if match:
                from_frame = int(match.group(1))
    if frames is None or from_frame is None:
        raise AnalysisError(f"{path}: 採取窓メタデータが無く必要区間を保証できない")
    if from_frame > after_frame or frames < through_frame:
        raise AnalysisError(
            f"{path}: 必要区間 frame {after_frame}以上 {through_frame}未満が"
            "採取窓に全て入っていない"
        )


def bit_domain(values: list[int], bit: int) -> frozenset[int]:
    return frozenset((value >> bit) & 1 for value in values)


def compare_bits(
    title: str,
    no_values: list[int],
    normal_values: list[int],
    definitions: tuple[tuple[int, str], ...],
    reference: str,
) -> tuple[list[str], int, int]:
    lines = [f"## {title}", reference]
    differences = comparable = 0
    if not no_values and not normal_values:
        lines.append("結果: 比較不能（両条件とも観測なし）")
        return lines, differences, comparable
    if not no_values or not normal_values:
        lines.append("結果: 比較不能（片条件のみ観測。ビット値差とは数えない）")
        return lines, differences, comparable
    for bit, name in definitions:
        comparable += 1
        differs = bit_domain(no_values, bit) != bit_domain(normal_values, bit)
        differences += int(differs)
        lines.append(f"bit{bit} {name}: {'差あり' if differs else '差なし'}")
    return lines, differences, comparable


def load(path: Path, after_frame: int) -> tuple[list[m2s.Ev], list[awp.Command]]:
    dropped = dropped_events(path)
    if dropped:
        raise AnalysisError(f"{path}: I/Oログに取りこぼしがあるため不採用")
    rows, masked = m2s.parse_iolog(path)
    rows = [row for row in rows if row.frame >= after_frame]
    if not rows:
        raise AnalysisError(f"{path}: 指定フレーム以後のイベントが無い")
    fdc_masked = sum(
        count for (cpu, port, _kind), count in masked.items()
        if cpu == "sub" and port in ("00FA", "00FB")
    )
    if fdc_masked:
        raise AnalysisError(f"{path}: FDC 値が伏せ字のため公開ビットを比較できない")
    # I/O採取を途中frameから開始すると、先頭がFDCコマンドのパラメータ途中に
    # なる可能性がある。この解析の基準イベントである、完全なSENSE DRIVE
    # STATUS (OUT command, OUT parameter, IN result) の初出まで$FBだけを捨て、
    # コマンド境界へ同期する。その他ポートの同じ窓の行は捨てない。
    fb = [row for row in rows if row.cpu == "sub" and row.port == "00FB"]
    sync_clock = None
    for index in range(len(fb) - 2):
        if (fb[index].kind == "OUT" and fb[index].value is not None
                and fb[index].value & 0x1F == 0x04
                and fb[index + 1].kind == "OUT"
                and fb[index + 2].kind == "IN"):
            sync_clock = fb[index].clock
            break
    if sync_clock is not None:
        parse_rows = [
            row for row in rows
            if not (row.cpu == "sub" and row.port == "00FB" and row.clock < sync_clock)
        ]
    else:
        parse_rows = rows
    return rows, awp.parse_commands(parse_rows)


def status_samples(commands: list[awp.Command]) -> dict[str, list[int]]:
    samples: dict[str, list[int]] = collections.defaultdict(list)
    previous_opcode: int | None = None
    for command in commands:
        values = command.input_values or []
        if command.opcode == 0x04 and values:
            samples["SENSE DRIVE STATUS / ST3"].append(values[-1])
        elif command.opcode == 0x06 and len(values) >= 7:
            tail = values[-7:]
            for index, field in enumerate(("ST0", "ST1", "ST2")):
                samples[f"READ DATA / {field}"].append(tail[index])
        elif command.opcode == 0x08 and values:
            samples["SENSE INTERRUPT STATUS / ST0"].append(values[0])
            if previous_opcode == 0x0F:
                samples["SEEK 後 SENSE INTERRUPT STATUS / ST0"].append(values[0])
            elif previous_opcode == 0x07:
                samples["RECALIBRATE 後 SENSE INTERRUPT STATUS / ST0"].append(values[0])
        previous_opcode = command.opcode
    return samples


def command_duration_signatures(commands: list[awp.Command]) -> dict[int, list[int]]:
    signatures: dict[int, list[int]] = collections.defaultdict(list)
    for command in commands:
        end_clock = getattr(command, "end_clock", command.clock)
        signatures[command.opcode].append(end_clock - command.clock)
    return signatures


def completion_signature(command: awp.Command) -> str:
    if command.opcode in awp.NO_RESULT:
        return "結果相なし"
    if command.opcode == 0x04:
        return "完了" if command.result_bytes >= 1 else "未完了"
    if command.opcode == 0x08:
        return "完了" if command.result_bytes in (1, 2) else "未完了"
    return "完了" if command.result_bytes >= 7 else "未完了"


def temporal_lines(
    no_rows: list[m2s.Ev], no_commands: list[awp.Command],
    normal_rows: list[m2s.Ev], normal_commands: list[awp.Command],
    reference: str,
) -> list[str]:
    lines = ["## 時間・完了外形", reference]
    names = (0x04, 0x06, 0x0F, 0x07, 0x08)
    no_durations = command_duration_signatures(no_commands)
    normal_durations = command_duration_signatures(normal_commands)
    for opcode in names:
        no_group = [c for c in no_commands if c.opcode == opcode]
        normal_group = [c for c in normal_commands if c.opcode == opcode]
        name = awp.NAMES[opcode]
        count_diff = len(no_group) != len(normal_group)
        no_completion = {completion_signature(c) for c in no_group}
        normal_completion = {completion_signature(c) for c in normal_group}
        completion_diff = no_completion != normal_completion
        duration_diff = set(no_durations[opcode]) != set(normal_durations[opcode])
        lines.append(
            f"{name}: 発行件数={'差あり' if count_diff else '差なし'}"
            f"（no_disk {len(no_group)}件／正常 {len(normal_group)}件）、"
            f"完了状態={'差あり' if completion_diff else '差なし'}、"
            f"所要clock集合={'差あり' if duration_diff else '差なし'}"
        )
    no_timeout = sum(1 for row in no_rows if row.cpu == "sub" and row.kind == "OUT"
                     and row.port == "00F9")
    normal_timeout = sum(1 for row in normal_rows if row.cpu == "sub" and row.kind == "OUT"
                         and row.port == "00F9")
    lines.append(
        "自作subタイムアウト印: "
        f"{'差あり' if bool(no_timeout) != bool(normal_timeout) else '差なし'}"
        f"（no_disk {no_timeout}件／正常 {normal_timeout}件）"
    )
    return lines


def sense_density(commands: list[awp.Command], first_frame: int,
                  through_frame: int, *, fault_constant: bool = False) -> dict[str, object]:
    """SENSE DRIVE STATUS の発行密度。値は一切扱わず、件数だけを返す。"""
    if through_frame <= first_frame:
        raise AnalysisError("密度窓の終端は開始フレームより後でなければならない")
    frame_counts = collections.Counter(
        command.frame for command in commands
        if command.opcode == 0x04 and first_frame <= command.frame < through_frame
    )
    counts = [frame_counts.get(frame, 0) for frame in range(first_frame, through_frame)]
    if fault_constant and counts:
        # selftest専用の故障注入点。実測CLIからは到達させない。
        counts = [counts[0]] * len(counts)
    return {
        "total": sum(counts),
        "frames": len(counts),
        "minimum": min(counts),
        "maximum": max(counts),
        "varying": len(set(counts)) > 1,
    }


def format_rate(total: int, frames: int) -> str:
    return f"{total / frames:.3f}件/F"


def density_lines(
    official_rows: list[m2s.Ev], official_commands: list[awp.Command],
    intervention_rows: list[m2s.Ev],
    intervention_commands: list[awp.Command], first_frame: int, through_frame: int,
    official_meta: dict[str, str], intervention_meta: dict[str, str],
    *, density_fault_constant: bool = False,
) -> list[str]:
    official = sense_density(official_commands, first_frame, through_frame,
                             fault_constant=density_fault_constant)
    intervention = sense_density(intervention_commands, first_frame, through_frame,
                                 fault_constant=density_fault_constant)
    official_total = int(official["total"])
    intervention_total = int(intervention["total"])
    if official_total == 0 or intervention_total == 0:
        raise AnalysisError("密度窓内で両条件の SENSE DRIVE STATUS を観測できない")
    official_response_count = sum(
        row.cpu == "sub" and row.kind == "OUT" and row.port == "00FC"
        for row in official_rows
        if first_frame <= row.frame < through_frame
    )
    intervention_response_count = sum(
        row.cpu == "sub" and row.kind == "OUT" and row.port == "00FC"
        for row in intervention_rows
        if first_frame <= row.frame < through_frame
    )
    if intervention_response_count:
        raise AnalysisError(
            "混成介入no_disk窓内にsub→main応答があり、応答欠落を確認できない")
    ratio = Fraction(intervention_total, official_total)
    frames = int(official["frames"])
    m7ci_count = 51800
    if official_total == m7ci_count:
        m7ci_result = "件数一致"
    else:
        m7ci_result = "件数不一致"
    return [
        "## SENSE DRIVE STATUS 反復密度",
        comparison_ref(official_meta, intervention_meta),
        f"測定窓: frame {first_frame}以上 {through_frame}未満（{frames}F）",
        f"公式ROM一式・no_disk: "
        f"{official_total}件、{format_rate(official_total, frames)}、"
        f"単位F範囲 {official['minimum']}..{official['maximum']}件",
        f"混成介入・no_disk: "
        f"{intervention_total}件、{format_rate(intervention_total, frames)}、"
        f"単位F範囲 {intervention['minimum']}..{intervention['maximum']}件",
        f"密度比（混成介入/公式ROM一式）: {float(ratio):.3f}倍"
        f"（件数比 {ratio.numerator}:{ratio.denominator}）",
        f"公式ROM一式・no_disk窓内のsub→main応答: {official_response_count}件",
        f"混成介入・no_disk窓内のsub→main応答: {intervention_response_count}件（応答欠落を確認）",
        f"m7ci入口判定区間51800件との照合: {m7ci_result}"
        f"（今回の公式採取窓は{official_total}件）",
        "注記: m7ciの入口判定区間と今回のframe窓は区間定義が異なる。"
        "不一致を換算で合わせず、観測系を再確認する材料として残す。",
        "注記: 介入へ公式同調用の待ち命令は追加していない。800F実行を維持し、",
        "打鍵以降の必要区間を拡大I/Oバッファへ全て記録した。",
        "公式の待ち間隔を仕様化するものではない。",
    ]


def report(no_path: Path, normal_path: Path, after_frame: int,
           no_meta_path: Path, normal_meta_path: Path,
           official_path: Path | None = None, official_meta_path: Path | None = None,
           intervention_path: Path | None = None,
           intervention_meta_path: Path | None = None, through_frame: int | None = None,
           suite_state: str = "単独解析", *, density_fault_constant: bool = False,
           require_full_window: bool = False) -> str:
    no_meta = load_run_metadata(no_meta_path, "mixed_no_disk")
    normal_meta = load_run_metadata(normal_meta_path, "mixed_normal")
    official_meta = (load_run_metadata(official_meta_path, "official_no_disk")
                     if official_meta_path is not None else None)
    intervention_meta = (load_run_metadata(intervention_meta_path, "mixed_intervention")
                         if intervention_meta_path is not None else None)
    if (official_path is None) != (official_meta is None):
        raise AnalysisError("公式runと公式runメタデータは対で指定すること")
    if (intervention_path is None) != (intervention_meta is None):
        raise AnalysisError("介入runと介入runメタデータは対で指定すること")
    if require_full_window:
        if through_frame is None:
            raise AnalysisError("採取窓検査には終端frameが必要")
        require_capture_window(no_path, after_frame, through_frame)
        require_capture_window(normal_path, after_frame, through_frame)
        if official_path is not None:
            require_capture_window(official_path, after_frame, through_frame)
        if intervention_path is not None:
            require_capture_window(intervention_path, after_frame, through_frame)
    no_rows, no_commands = load(no_path, after_frame)
    normal_rows, normal_commands = load(normal_path, after_frame)
    official_rows = official_commands = None
    if official_path is not None:
        official_rows, official_commands = load(official_path, after_frame)
    if through_frame is None:
        through_frame = max(row.frame for row in no_rows + normal_rows) + 1
    no_status, normal_status = status_samples(no_commands), status_samples(normal_commands)
    mixed_reference = comparison_ref(no_meta, normal_meta)

    sections: list[str] = [
        "# 混成既定no_disk と混成既定正常B: の自作sub可視信号比較",
        "",
        f"測定一式の状態: {suite_state}",
        "",
        "run構成:",
        f"- {run_ref(no_meta)}（条件: no_disk）",
        f"- {run_ref(normal_meta)}（条件: 正常B:）",
        *([f"- {run_ref(official_meta)}（条件: no_disk）"] if official_meta else []),
        *([f"- {run_ref(intervention_meta)}（条件: no_disk）"] if intervention_meta else []),
        "",
        "判定規則: 各公開ビットで、条件内に観測された0/1の集合だけを比較する。",
        "生値・値列は出力しない。発行回数や時間差はビット差から分離する。",
        "",
    ]
    total_differences = total_comparable = 0
    targets = (
        ("SENSE DRIVE STATUS / ST3", ST3_BITS),
        ("READ DATA / ST0", ST0_BITS),
        ("READ DATA / ST1", ST1_BITS),
        ("READ DATA / ST2", ST2_BITS),
        ("SENSE INTERRUPT STATUS / ST0", ST0_BITS),
        ("SEEK 後 SENSE INTERRUPT STATUS / ST0", ST0_BITS),
        ("RECALIBRATE 後 SENSE INTERRUPT STATUS / ST0", ST0_BITS),
    )
    for title, definitions in targets:
        lines, differences, comparable = compare_bits(
            title, no_status[title], normal_status[title], definitions, mixed_reference
        )
        sections.extend(lines + [""])
        total_differences += differences
        total_comparable += comparable

    sections.extend([
        "## SEEK / RECALIBRATE の直接結果相",
        mixed_reference,
        "ST0/ST1/ST2: 該当なし（公開仕様上、両コマンドに直接の結果相はない。",
        "完了通知は後続の SENSE INTERRUPT STATUS / ST0 として上で比較した）",
        "",
    ])
    no_msr = [row.value for row in no_rows if row.cpu == "sub" and row.kind == "IN"
              and row.port == "00FA" and row.value is not None]
    normal_msr = [row.value for row in normal_rows if row.cpu == "sub" and row.kind == "IN"
                  and row.port == "00FA" and row.value is not None]
    lines, differences, comparable = compare_bits(
        "FDC MSR", no_msr, normal_msr, MSR_BITS, mixed_reference)
    sections.extend(lines + [""])
    total_differences += differences
    total_comparable += comparable

    # $FBはFDCのデータ相（媒体本文を含み得る）なので、生値はもちろん
    # 包含集合の比較対象にもせず、上で結果相だけを公開フィールドへ射影した。
    # $FAはMSRとして上で比較済み。それ以外のsub入力ポートは意味を付けず、
    # 各bitの観測集合差だけを追加の候補として洗う。
    sections.extend(["## その他の自作sub入力ポート", mixed_reference, ""])
    other_ports = sorted(
        {row.port for row in no_rows + normal_rows
         if row.cpu == "sub" and row.kind == "IN" and row.port not in ("00FA", "00FB")}
    )
    other_differences = other_comparable = 0
    if not other_ports:
        sections.append("比較対象ポート: 観測なし")
    for port in other_ports:
        no_values = [row.value for row in no_rows if row.cpu == "sub" and row.kind == "IN"
                     and row.port == port and row.value is not None]
        normal_values = [row.value for row in normal_rows
                         if row.cpu == "sub" and row.kind == "IN"
                         and row.port == port and row.value is not None]
        lines, differences, comparable = compare_bits(
            f"IN ${port[-2:]}", no_values, normal_values,
            tuple((bit, f"bit{bit}") for bit in range(7, -1, -1)),
            mixed_reference,
        )
        sections.extend(lines + [""])
        other_differences += differences
        other_comparable += comparable
    sections.extend(temporal_lines(
        no_rows, no_commands, normal_rows, normal_commands, mixed_reference) + [""])
    if total_comparable == 0:
        raise AnalysisError(
            "比較可能な公開ビットが0項目（結果ではなく測定失敗）"
        )
    if intervention_path is not None and official_rows is not None:
        intervention_rows, intervention_commands = load(intervention_path, after_frame)
        sections.extend(density_lines(
            official_rows, official_commands, intervention_rows, intervention_commands,
            after_frame, through_frame,
            official_meta, intervention_meta,
            density_fault_constant=density_fault_constant,
        ) + [""])
    else:
        sections.extend([
            "## SENSE DRIVE STATUS 反復密度",
            "参照run: 公式runまたは混成介入runが未採用のため比較不能（部分結果）。",
            "",
        ])
    sections.extend([
        "## 集計",
        mixed_reference,
        f"比較可能な公開ビット: {total_comparable}項目",
        f"差を検出した公開ビット: {total_differences}項目",
        f"その他ポートの比較可能bit: {other_comparable}項目",
        f"その他ポートで差を検出したbit: {other_differences}項目",
        "注意: 時間差とMSR差はエミュレータのFDC/PIO実装にも依存し、",
        "その他ポートのbit差には公開上の意味を付けていない。いずれも、それだけでは",
        "実機で成立する媒体検出信号とは確定しない。",
    ])
    return "\n".join(sections) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-disk", required=True, type=Path)
    parser.add_argument("--no-disk-meta", required=True, type=Path)
    parser.add_argument("--normal", required=True, type=Path)
    parser.add_argument("--normal-meta", required=True, type=Path)
    parser.add_argument("--official", type=Path)
    parser.add_argument("--official-meta", type=Path)
    parser.add_argument("--intervention", type=Path)
    parser.add_argument("--intervention-meta", type=Path)
    parser.add_argument("--after-frame", type=int, default=700)
    parser.add_argument("--through-frame", type=int)
    parser.add_argument("--suite-state", default="単独解析")
    parser.add_argument("--require-full-window", action="store_true",
                        help="必要区間全体が採取窓に入る測定条件を必須にする")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        text = report(args.no_disk, args.normal, args.after_frame,
                      args.no_disk_meta, args.normal_meta,
                      args.official, args.official_meta,
                      args.intervention, args.intervention_meta,
                      args.through_frame, args.suite_state,
                      require_full_window=args.require_full_window)
    except (OSError, AnalysisError, awp.SafeError) as exc:
        print(f"解析不能: {exc}", file=sys.stderr)
        return 2
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
