#!/usr/bin/env python3
"""tools/cmp_io.py — q88measure --io-log の出力を比較する。

docs/spec/l1-ipl.md 第6節「実装要件（適合条件）」・第7節「検証方法」を
実行可能にしたもの。自作 IPL を書く前に用意する物差し。

使い方:
    tools/cmp_io.py <基準.iolog.txt> <対象.iolog.txt> [--cpu main|sub] [--with-in]
    tools/cmp_io.py <基準> <対象> --init N --cycle M     ← 2 段階の適合条件

--with-in は構造比較の参考情報であり、適合条件ではない（第6節「比較しないもの」）。

## --init / --cycle を足した理由

第6節の適合条件は 2 段階（第3版で3段階になった）である。

  ① 初期化区間: 先頭 N 件（L1 では 350）が順序・ポート・値まで完全一致
  ② 定常状態:   N+1 件目以降が M 件（L1 では 7）の周期の繰り返し。
                **繰り返しの回数は問わない**
  ③ 定常状態に `IN 40`（VRTC ポーリング）が現れないこと（第3版・第6節③）。
                定常状態は VSYNC 割り込み駆動であり、垂直帰線を
                ポーリングで待ってはいない。VRTC ポーリングで組んだ
                実装は①②を満たしたまま③で落ちる——それが狙いである。

列全体を突き合わせる既定モードでは ② が扱えない。自作 IPL は BASIC の
初期化を行わないぶん早く定常状態に入るので、同じ 60 フレームでも周回数が
増える。**回数を条件に入れると「速い実装が速い」というだけで不合格になる。**
IN の回数を適合条件から外したのとまったく同じ理由である。

実際、L1 の自作 IPL は 728 件（初期化 350 + 7×54 周）を出し、公式版の
560 件（350 + 7×30 周）と先頭 560 件まで一致したうえで
「対象側が長い（余分）」と報告された。物差しのほうが条件に追いついていない。

③ は IN も見る必要があるので、OUT だけを抜き出した列（① ② が使う列）とは
別に、CPU 節の全イベント（IN + OUT、発生順そのまま）も使う。
「① の N 件目の OUT が全体の何番目に当たるか」を境目として、それより後ろに
`IN 40` が無いかを見る。

終了コード: 一致 0 / 不一致 1 / 使い方の誤り 2
"""

import argparse
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    seq: int
    frame: int
    cpu: str
    kind: str  # "IN" / "OUT"
    port: str
    value: str
    pc: str
    clock: int | None = None  # 共通クロック（0010-shared-clock.patch）。旧形式(7列)では None


class FormatError(Exception):
    """入力ファイルの書式が壊れている。"""


def parse_iolog(path: str, cpu: str) -> list[Event]:
    """指定 CPU (main/sub) の節から全イベントを読み取る。

    節が見つからない、または列数が足りない行があれば FormatError。
    """
    section_header = f"# {cpu}"
    events: list[Event] = []
    in_section = False
    section_found = False
    saw_any_line_in_section = False

    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")
            stripped = line.strip()

            if stripped == section_header:
                in_section = True
                section_found = True
                continue

            if not in_section:
                continue

            # 次の節（"# main" / "# sub"）に入ったら終わり
            if stripped.startswith("# ") and stripped not in (
                section_header,
                "# seq  frame  cpu   kind  port  value  pc",
            ):
                # 他のコメント行（ヘッダ再掲・注記等）は読み飛ばす
                if stripped.startswith("# main") or stripped.startswith("# sub"):
                    break
                continue

            if stripped == "" or stripped.startswith("#"):
                continue

            saw_any_line_in_section = True
            fields = stripped.split()
            # 2形式ある。
            #   旧形式(7列): seq frame cpu kind port value pc
            #   新形式(8列): seq clock frame cpu kind port value pc
            #                （0010-shared-clock.patch 導入後。m6c以降で使用）
            # 新形式を「列数が7でない」で弾いていたのが未検証の穴だった
            # （docs/notes/m6-conformance.md 参照）。両方読めるようにする。
            clock: int | None
            if len(fields) == 7:
                seq_s, frame_s, ev_cpu, kind, port, value, pc = fields
                clock_s = None
            elif len(fields) == 8:
                seq_s, clock_s, frame_s, ev_cpu, kind, port, value, pc = fields
            else:
                raise FormatError(
                    f"{path}:{lineno}: 列数が7でも8でもない({len(fields)}列): {stripped!r}"
                )
            if kind not in ("IN", "OUT"):
                raise FormatError(
                    f"{path}:{lineno}: kind が IN/OUT でない: {stripped!r}"
                )
            try:
                seq = int(seq_s)
                frame = int(frame_s)
                clock = int(clock_s) if clock_s is not None else None
            except ValueError as e:
                raise FormatError(f"{path}:{lineno}: seq/frame/clock が整数でない: {stripped!r}") from e

            events.append(Event(seq, frame, ev_cpu, kind, port, value, pc, clock))

    if not section_found:
        raise FormatError(f"{path}: '# {cpu}' 節が見つからない")

    _ = saw_any_line_in_section  # 0件自体はエラーにしない（節はあるが本当に0件の場合がある）
    return events


def filter_out_only(events: list[Event]) -> list[Event]:
    return [e for e in events if e.kind == "OUT"]


def normalize_port(port: str) -> str:
    """'FD' / '0xfd' / '00FD' などを、ログの表記(4桁16進・大文字)に揃える。"""
    p = port.strip()
    if p.lower().startswith("0x"):
        p = p[2:]
    if len(p) > 4 or not all(c in "0123456789abcdefABCDEF" for c in p):
        raise FormatError(f"--port の値が16進数として不正: {port!r}")
    return p.upper().zfill(4)


def filter_port_kind(events: list[Event], kind: str, port: str) -> list[Event]:
    """指定 kind・port の列だけを、発生順そのままで取り出す。

    docs/spec/l3-subrom.md 5.1節「メインCPUが最終的に受け取るデータ列」を
    機械的に見るためのフィルタ。M6 のバースト（1回限り・非周期）は
    L1型の --init/--cycle が当てはまらないため、「特定ポートの列を
    丸ごと完全一致で見る」という、この既定モード寄りの単純な比較のほうが
    向いている（docs/notes/m6-conformance.md）。
    """
    p = normalize_port(port)
    return [e for e in events if e.kind == kind and e.port == p]


def fold_in_runs(events: list[Event]) -> list[Event]:
    """--with-in 用: 同一ポートへの連続する IN を1件に畳む（最後の値を残す）。

    OUT はそのまま通す。連続 IN の連なりが終わったら、その連なりの
    最後のイベント（ポートと最終値）だけを列に加える。
    """
    result: list[Event] = []
    run: list[Event] = []

    def flush():
        if run:
            result.append(run[-1])
            run.clear()

    for e in events:
        if e.kind == "IN":
            if run and run[-1].port == e.port:
                run.append(e)
            else:
                flush()
                run.append(e)
        else:
            flush()
            result.append(e)
    flush()
    return result


def classify_mismatch(base: list[Event], target: list[Event], idx: int) -> str:
    """idx 番目（0-indexed）での食い違いの種類を分類する。"""
    base_has = idx < len(base)
    target_has = idx < len(target)
    if not base_has and target_has:
        return "対象側が長い（余分）"
    if base_has and not target_has:
        return "基準側が長い（対象に足りない）"
    b, t = base[idx], target[idx]
    if b.port != t.port:
        return "ポートが違う"
    if b.value != t.value:
        return "値が違う"
    return "種別が違う" if b.kind != t.kind else "不明な差異"


def fmt_event(e: Event | None) -> str:
    if e is None:
        return "(なし)"
    return f"{e.kind:<3} port={e.port} value={e.value}  (seq={e.seq} frame={e.frame} pc={e.pc})"


def report_mismatch(base: list[Event], target: list[Event], mode_label: str) -> int:
    n = min(len(base), len(target))
    first_diff = None
    for i in range(n):
        b, t = base[i], target[i]
        if b.port != t.port or b.value != t.value or b.kind != t.kind:
            first_diff = i
            break
    if first_diff is None:
        if len(base) != len(target):
            first_diff = n  # 片方が末尾で尽きている
        else:
            # 完全一致
            return 0

    kind = classify_mismatch(base, target, first_diff)

    print(f"[{mode_label}] 不一致: {first_diff + 1} 件目で食い違い")
    print(f"  種類: {kind}")
    print(f"  基準側: 総 {len(base)} 件 / 対象側: 総 {len(target)} 件")
    print(f"  ここまで一致: {first_diff} 件")
    print()

    lo = max(0, first_diff - 5)
    hi = min(max(len(base), len(target)), first_diff + 6)
    print(f"  --- 前後 (基準側 index {lo+1}〜{hi} ) ---")
    for i in range(lo, hi):
        marker = "→" if i == first_diff else " "
        b = base[i] if i < len(base) else None
        print(f"  {marker} 基準[{i+1:>6}] {fmt_event(b)}")
    print()
    print(f"  --- 前後 (対象側 index {lo+1}〜{hi} ) ---")
    for i in range(lo, hi):
        marker = "→" if i == first_diff else " "
        t = target[i] if i < len(target) else None
        print(f"  {marker} 対象[{i+1:>6}] {fmt_event(t)}")

    return 1


def check_cycle(seq: list[Event], n_init: int, cycle: list[tuple[str, str]],
                side: str) -> tuple[str | None, int, int]:
    """n_init 件目以降が cycle の繰り返しかを見る。

    末尾は周期の途中で切れてよい（測定はフレーム数で打ち切られるため）。
    ただし **1 周も回っていなければ不合格** にする。そうしないと
    「定常状態に入る前に落ちた記録」が黙って通ってしまう。

    返り値: (エラー文字列 or None, 周回数, 端数)
    """
    tail = seq[n_init:]
    m = len(cycle)
    if len(tail) < m:
        return (f"{side}: 定常状態が 1 周も回っていない"
                f"（{n_init} 件目以降が {len(tail)} 件、周期は {m} 件）", 0, len(tail))
    for i, e in enumerate(tail):
        want = cycle[i % m]
        if (e.port, e.value) != want:
            return (f"{side}: {n_init + i + 1} 件目が周期から外れる"
                    f"（周期の {i % m + 1} 番目: 期待 port={want[0]} value={want[1]} ／ "
                    f"実際 port={e.port} value={e.value}）", 0, 0)
    return None, len(tail) // m, len(tail) % m


STEADY_FORBIDDEN_IN_PORT = 0x40  # 仕様書 第6節③。VRTC ポーリング（第5a節①）


def out_boundary_index(events: list[Event], n_out: int) -> int:
    """全イベント列（IN+OUT、発生順）の中で、OUT が n_out 件目に達した
    直後のインデックスを返す。

    n_out 件に満たなければ len(events) を返す（定常状態がまだ無いので、
    その側については③の検査対象が空になる＝検査を素通りする）。
    """
    count = 0
    for i, e in enumerate(events):
        if e.kind == "OUT":
            count += 1
            if count == n_out:
                return i + 1
    return len(events)


def check_no_steady_in_port(events: list[Event], boundary: int, port: int,
                             side: str) -> str | None:
    """境目（boundary）より後ろに、指定ポートへの IN が無いことを見る。

    仕様書 第6節③「定常状態に `IN 40` が現れないこと」の実行部分。
    """
    for e in events[boundary:]:
        if e.kind != "IN":
            continue
        try:
            p = int(e.port, 16)
        except ValueError:
            continue
        if p == port:
            return (f"{side}: 定常状態に IN {port:02X} が現れる"
                    f"（seq={e.seq} frame={e.frame} pc={e.pc}）")
    return None


def run_two_stage(base_events: list[Event], target_events: list[Event],
                  n_init: int, m_cycle: int) -> int:
    """第6節の 3 段階の適合条件で判定する（① ② ③。③ は第3版で追加）。

    base_events / target_events は CPU 節の全イベント（IN + OUT、発生順）。
    ① ② は OUT だけを取り出した列で見る。③ は IN も見る必要があるので、
    全イベント列のほうを使う。
    """
    label = f"3段階（初期化 {n_init} 件の完全一致 ／ 以降 {m_cycle} 件周期 ／ ③IN40無し）"

    base_seq = filter_out_only(base_events)
    target_seq = filter_out_only(target_events)

    need = n_init + m_cycle
    if len(base_seq) < need:
        print(f"[{label}] エラー: 基準側が短すぎる"
              f"（{len(base_seq)} 件。周期を取り出すのに {need} 件必要）", file=sys.stderr)
        return 2

    # ① 初期化区間
    rc = report_mismatch(base_seq[:n_init], target_seq[:n_init],
                         f"{label} ① 初期化区間")
    if rc != 0:
        return rc

    # ② 定常状態。周期は基準側から取り出す
    cycle = [(e.port, e.value) for e in base_seq[n_init:need]]
    cycle_txt = " / ".join(f"{p}<-{v}" for p, v in cycle)

    err_b, laps_b, rest_b = check_cycle(base_seq, n_init, cycle, "基準側")
    err_t, laps_t, rest_t = check_cycle(target_seq, n_init, cycle, "対象側")
    if err_b or err_t:
        print(f"[{label}] 不一致: ② 定常状態が周期になっていない")
        print(f"  周期: {cycle_txt}")
        for e in (err_b, err_t):
            if e:
                print(f"  {e}")
        return 1

    # ③ 定常状態に IN 40 が現れないこと（第3版・第6節③）
    base_boundary = out_boundary_index(base_events, n_init)
    target_boundary = out_boundary_index(target_events, n_init)
    err_b3 = check_no_steady_in_port(base_events, base_boundary,
                                      STEADY_FORBIDDEN_IN_PORT, "基準側")
    err_t3 = check_no_steady_in_port(target_events, target_boundary,
                                      STEADY_FORBIDDEN_IN_PORT, "対象側")
    if err_b3 or err_t3:
        print(f"[{label}] 不一致: ③ 定常状態に IN {STEADY_FORBIDDEN_IN_PORT:02X} が現れる"
              "（VRTC ポーリング駆動の疑い。第3版・第6節③）")
        for e in (err_b3, err_t3):
            if e:
                print(f"  {e}")
        return 1

    print(f"[{label}] 一致")
    print(f"  ① 初期化区間 {n_init} 件が完全一致")
    print(f"  ② 定常状態の周期: {cycle_txt}")
    print(f"     基準側 {laps_b} 周（端数 {rest_b} 件） ／ "
          f"対象側 {laps_t} 周（端数 {rest_t} 件）")
    print("     周回数は適合条件ではない（第6節「比較しないもの」）")
    print(f"  ③ 定常状態に IN {STEADY_FORBIDDEN_IN_PORT:02X} なし（VSYNC 割り込み駆動）")
    return 0


def run_compare(base_events: list[Event], target_events: list[Event], with_in: bool) -> int:
    if with_in:
        base_seq = fold_in_runs(base_events)
        target_seq = fold_in_runs(target_events)
        label = "--with-in（参考情報。これは適合条件ではない）"
    else:
        base_seq = filter_out_only(base_events)
        target_seq = filter_out_only(target_events)
        label = "OUT のみ（適合条件）"

    if len(base_seq) == 0 and len(target_seq) == 0:
        print(f"[{label}] エラー: 両側とも比較対象のイベントが0件。比較になっていない。", file=sys.stderr)
        return 2

    rc = report_mismatch(base_seq, target_seq, label)
    if rc == 0:
        kind_word = "イベント" if with_in else "OUT"
        print(f"[{label}] 一致（{kind_word} {len(base_seq)}件）")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="q88measure --io-log の出力2つを比較する（docs/spec/l1-ipl.md 第6・7節）"
    )
    parser.add_argument("base", help="基準の .iolog.txt")
    parser.add_argument("target", help="対象の .iolog.txt")
    parser.add_argument("--cpu", choices=["main", "sub"], default="main", help="比較する CPU（既定: main）")
    parser.add_argument("--with-in", action="store_true", help="畳んだ IN も含めて構造を比較する（参考。適合条件ではない）")
    parser.add_argument("--init", type=int, default=None, metavar="N",
                        help="2段階判定: 先頭 N 件を完全一致で比べる（L1 は 350）")
    parser.add_argument("--cycle", type=int, default=None, metavar="M",
                        help="2段階判定: N 件目以降を M 件の周期とみなす（L1 は 7）")
    parser.add_argument("--port", type=str, default=None, metavar="PORT",
                        help="特定ポート判定: 指定ポート(例 FD, 00FD)に絞り、"
                             "発生順のまま完全一致で比べる（--kind と併用必須）。"
                             "M6のような非周期の一括転送向け（docs/notes/m6-conformance.md）")
    parser.add_argument("--kind", choices=["IN", "OUT"], default=None,
                        help="特定ポート判定: 見る方向（--port と併用必須）")
    args = parser.parse_args()

    if (args.init is None) != (args.cycle is None):
        print("エラー: --init と --cycle は両方指定する", file=sys.stderr)
        return 2
    if (args.port is None) != (args.kind is None):
        print("エラー: --port と --kind は両方指定する", file=sys.stderr)
        return 2
    if args.init is not None:
        if args.init < 0 or args.cycle < 1:
            print("エラー: --init は 0 以上、--cycle は 1 以上", file=sys.stderr)
            return 2
        if args.with_in:
            print("エラー: --with-in は参考情報なので 2段階判定と併用しない", file=sys.stderr)
            return 2
        if args.port is not None:
            print("エラー: --init/--cycle と --port/--kind は併用しない", file=sys.stderr)
            return 2
    if args.port is not None and args.with_in:
        print("エラー: --with-in と --port/--kind は併用しない", file=sys.stderr)
        return 2

    try:
        base_events = parse_iolog(args.base, args.cpu)
        target_events = parse_iolog(args.target, args.cpu)
    except FormatError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"エラー: ファイルを読めない: {e}", file=sys.stderr)
        return 2

    if args.init is not None:
        base_seq = filter_out_only(base_events)
        target_seq = filter_out_only(target_events)
        if len(base_seq) == 0 and len(target_seq) == 0:
            print("エラー: 両側とも OUT が0件。比較になっていない。", file=sys.stderr)
            return 2
        return run_two_stage(base_events, target_events, args.init, args.cycle)

    if args.port is not None:
        try:
            base_seq = filter_port_kind(base_events, args.kind, args.port)
            target_seq = filter_port_kind(target_events, args.kind, args.port)
        except FormatError as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 2
        if len(base_seq) == 0 and len(target_seq) == 0:
            print(f"エラー: 両側とも {args.kind} {normalize_port(args.port)} が0件。比較になっていない。",
                  file=sys.stderr)
            return 2
        label = f"{args.kind} {normalize_port(args.port)} のみ（完全一致・非周期）"
        rc = report_mismatch(base_seq, target_seq, label)
        if rc == 0:
            print(f"[{label}] 一致（{len(base_seq)}件）")
        return rc

    return run_compare(base_events, target_events, args.with_in)


if __name__ == "__main__":
    sys.exit(main())
