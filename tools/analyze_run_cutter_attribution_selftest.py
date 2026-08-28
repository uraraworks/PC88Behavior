#!/usr/bin/env python3
"""m7di: run切り出し帰属器(analyze_run_cutter_attribution.py)自体の陰性対照。

「常に失敗する検出器は故障注入を必ず通過する」「合格条件が失敗状態のほうを
強く満たす」という過去事故を踏まえ、m7dhのFE系M判定が依拠した
「アンカーcutでは例外が0件になる」という結果が、アンカーが常に0を返す
壊れ方によるものではないことを、この帰属器自体に対して検算する。

検査は3種類に分ける。

1. 分類器の出し分け(単体): relation()/classify_group()/run_relation()/
   classify_send()を直接呼び、boundary_match・false_split・false_merge・
   interrupt_boundary・log_endpoint・unanchoredの6カテゴリすべてを、
   FE系・SEND系それぞれ独立に作り分けられることを確認する。全部を1カテゴリへ
   落とす壊れ方をしていないことの検出力確認。
2. アンカーの陰性対照(FE系・パイプライン全体): 境界は一切崩さず、値だけに
   本物のbit0規則違反を仕込んだ合成ログを作る。境界が正しい以上、現cutと
   アンカーcutの両方が同じ例外を検出しなければならない。「アンカー例外0件」
   が意味のある検査であることを示す。
3. 同上の混在版: 本物の違反と、境界だけが壊れた偽の違反(spin分割)を混在させ、
   アンカーが本物だけを残し偽物を消すことを確認する。
4. アンカーの陰性対照(SEND run系): 境界を保ったまま`0F`規則・偶奇規則へ
   本物の違反を仕込み、現cut・アンカーcutの両方に例外が残ることを確認する。

公式ROM・公式ディスク・公式ログは一切使用しない。すべて規則生成した合成データ。
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import analyze_run_cutter_attribution as attrib  # noqa: E402

Ev = attrib.Ev


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, label: str, actual, expected) -> None:
        if actual == expected:
            print(f"OK  - {label}: {actual}")
        else:
            self.failures.append(f"{label}: 実測={actual!r}, 予測={expected!r}")
            print(f"NG  - {self.failures[-1]}")


R = Result()


# ==========================================================================
# 1. 分類器の出し分け(単体) — FE系(relation/classify_group)
# ==========================================================================

def ev(clock: int, *, cpu: str = "main", kind: str = "IN", port: str = "00FE",
       value: int = 0, pc: str = "0000") -> Ev:
    return Ev(clock, clock, 0, cpu, kind, port, value, pc)


def fe_classifier_categories() -> None:
    far_main_rows = [ev(1), ev(9999)]  # log端に触れないための遠い番兵

    # boundary_match: 現cutの境界とアンカーの境界が完全一致
    group = [ev(100), ev(110)]
    anchors = [[ev(100), ev(110)]]
    R.check("FE分類/boundary_match",
            attrib.classify_group(group, anchors, [], far_main_rows),
            "boundary_match")

    # false_split: 現cutがアンカーの真部分集合(真の呼出し途中で分割された)
    group = [ev(100), ev(110)]
    anchors = [[ev(100), ev(110), ev(120)]]
    R.check("FE分類/false_split",
            attrib.classify_group(group, anchors, [], far_main_rows),
            "false_split")

    # false_merge: 現cutが複数のアンカーへまたがる(偽結合)
    group = [ev(100), ev(200)]
    anchors = [[ev(100)], [ev(200)]]
    R.check("FE分類/false_merge",
            attrib.classify_group(group, anchors, [], far_main_rows),
            "false_merge")

    # unanchored: どのアンカーとも重ならない
    group = [ev(500)]
    anchors = [[ev(100)], [ev(200)]]
    R.check("FE分類/unanchored",
            attrib.classify_group(group, anchors, [], far_main_rows),
            "unanchored")

    # interrupt_boundary: 境界一致でも、直近に割り込み受理があれば優先される
    group = [ev(100), ev(110)]
    anchors = [[ev(100), ev(110)]]
    R.check("FE分類/interrupt_boundary(boundary_matchを上書き)",
            attrib.classify_group(group, anchors, [105], far_main_rows),
            "interrupt_boundary")

    # log_endpoint: ログ端に触れていれば、境界一致や割り込みより優先される
    main_rows = [ev(100), ev(110), ev(999)]
    group = [ev(100), ev(110)]
    anchors = [[ev(100), ev(110)]]
    R.check("FE分類/log_endpoint(境界一致・割り込みより優先)",
            attrib.classify_group(group, anchors, [105], main_rows),
            "log_endpoint")


# --- SEND系(run_relation/classify_send) ----------------------------------

def send_classifier_categories() -> None:
    main = [ev(i * 10, kind="OUT", port="00FD", pc="37F4") for i in range(20)]

    # boundary_match
    run = [5, 6]
    anchors = [[5, 6]]
    R.check("SEND分類/boundary_match",
            attrib.classify_send(run, None, anchors, main, [], [i for a in anchors for i in a]),
            "boundary_match")

    # false_split: 現cutのrunがアンカーの真部分集合
    run = [5, 6]
    anchors = [[5, 6, 7]]
    R.check("SEND分類/false_split",
            attrib.classify_send(run, None, anchors, main, [], []),
            "false_split")

    # false_merge: 現cutのrunが複数アンカーへまたがる
    run = [5, 10]
    anchors = [[5], [10]]
    R.check("SEND分類/false_merge",
            attrib.classify_send(run, None, anchors, main, [], []),
            "false_merge")

    # unanchored
    run = [5, 6]
    anchors = [[12, 13]]
    R.check("SEND分類/unanchored",
            attrib.classify_send(run, None, anchors, main, [], []),
            "unanchored")

    # interrupt_boundary: 境界一致でも、run区間内の割り込みが優先される
    run = [5, 6]
    anchors = [[5, 6]]
    R.check("SEND分類/interrupt_boundary(boundary_matchを上書き)",
            attrib.classify_send(run, None, anchors, main, [55], []),
            "interrupt_boundary")

    # log_endpoint: main列の先頭/末尾に触れるrunは境界一致より優先される
    run = [0, 1]
    anchors = [[0, 1]]
    R.check("SEND分類/log_endpoint(境界一致・割り込みより優先)",
            attrib.classify_send(run, None, anchors, main, [5], []),
            "log_endpoint")


# ==========================================================================
# 2〜4. パイプライン全体でのアンカー陰性対照
# ==========================================================================

@dataclass(frozen=True)
class Row:
    clock: int
    cpu: str
    kind: str
    port: str
    value: str
    pc: str


def write_iolog(path: Path, rows: list[Row]) -> None:
    lines = ["# 規則生成した合成ログ(公式データ不使用)",
             "# seq clock frame cpu kind port value pc"]
    for seq, row in enumerate(sorted(rows, key=lambda r: r.clock), 1):
        lines.append(f"{seq} {row.clock} 0 {row.cpu} {row.kind} "
                      f"{row.port} {row.value} {row.pc}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_empty_intlog(path: Path) -> None:
    path.write_text("# 規則生成した合成割り込みログ(割り込みなし・公式データ不使用)\n",
                     encoding="utf-8")


# --- FE系: 境界を崩さず値だけへ本物のbit0違反を仕込む ---------------------
#
# 各"呼出し"は OUT $FD(landmark) → recv_pre 2読取り → IN $FC(landmark) →
# recv_post 2読取り、という実プロトコル通りの構造を保つ。境界(landmark)は
# 一切省略・追加しない。genuine_pre/genuine_post に挙げた呼出し番号だけ、
# 末尾読取りのbit0をわざと逆にする(規則違反そのもの)。split_pre/split_postに
# 挙げた呼出し番号は、境界は保ったまま2読取りの間に無関係な別ポートI/Oを1件
# 挟み、現cutだけを分割させる(アンカーはlandmark区間の中身を丸ごと拾うので
# 影響を受けない)。

def build_fe_calls(n: int, *, genuine_pre: set[int] = frozenset(),
                    genuine_post: set[int] = frozenset(),
                    split_pre: set[int] = frozenset(),
                    split_post: set[int] = frozenset()) -> list[Row]:
    rows: list[Row] = []
    clock = 10

    def emit(cpu: str, kind: str, port: str, value: str, pc: str) -> None:
        nonlocal clock
        rows.append(Row(clock, cpu, kind, port, value, pc))
        clock += 10

    for i in range(n):
        emit("main", "OUT", "00FD", "--", "37F4")  # landmark: 選択開始
        entry_pre = "00"
        exit_pre = "00" if i in genuine_pre else "01"  # 正しくは末尾bit0=1
        emit("main", "IN", "00FE", entry_pre, "3853")
        if i in split_pre:
            emit("main", "IN", "00E4", "00", "3000")  # 無関係I/O(現cutだけ分割)
        emit("main", "IN", "00FE", exit_pre, "3853")
        emit("main", "IN", "00FC", "--", "3880")  # landmark: RECV(pre/post境界)
        entry_post = "01"
        exit_post = "01" if i in genuine_post else "00"  # 正しくは末尾bit0=0
        emit("main", "IN", "00FE", entry_post, "386F")
        if i in split_post:
            emit("main", "IN", "00E4", "00", "3000")
        emit("main", "IN", "00FE", exit_post, "386F")
    emit("main", "OUT", "00FD", "--", "37F4")  # 末尾landmark(ログ端の巻き添え防止)
    return rows


def fe_negative_control(tmp: Path) -> None:
    """A. 純粋な陰性対照: 本物の違反だけを仕込み、境界は一切崩さない。"""
    rows = build_fe_calls(6, genuine_pre={0, 1}, genuine_post={2, 3})
    iolog = tmp / "fe-negctl.iolog.txt"
    intlog = tmp / "fe-negctl.intlog.txt"
    write_iolog(iolog, rows)
    write_empty_intlog(intlog)
    result = attrib.analyze(iolog, intlog, "fe-negctl")
    pre, post = result["fe"]["recv_pre"], result["fe"]["recv_post"]

    R.check("FE陰性対照A/recv_pre 現cut例外", pre["current_exceptions"], 2)
    R.check("FE陰性対照A/recv_pre アンカー例外(0件に潰れないこと)",
            pre["anchor_exceptions"], 2)
    R.check("FE陰性対照A/recv_pre 帰属", pre["attribution"], {"boundary_match": 2})

    R.check("FE陰性対照A/recv_post 現cut例外", post["current_exceptions"], 2)
    R.check("FE陰性対照A/recv_post アンカー例外(0件に潰れないこと)",
            post["anchor_exceptions"], 2)
    R.check("FE陰性対照A/recv_post 帰属", post["attribution"], {"boundary_match": 2})


def fe_mixed_control(tmp: Path) -> None:
    """B. 本物の違反 + 境界だけが壊れた偽の違反を混在させる。

    アンカーは本物(2件)だけを残し、境界由来の偽物(1件)を消すこと、
    帰属も boundary_match(本物) と false_split(偽物) へ正しく分かれることを
    確認する。
    """
    rows = build_fe_calls(6, genuine_pre={0, 1}, genuine_post={2, 3},
                           split_pre={4}, split_post={5})
    iolog = tmp / "fe-mixed.iolog.txt"
    intlog = tmp / "fe-mixed.intlog.txt"
    write_iolog(iolog, rows)
    write_empty_intlog(intlog)
    result = attrib.analyze(iolog, intlog, "fe-mixed")
    pre, post = result["fe"]["recv_pre"], result["fe"]["recv_post"]

    R.check("FE混在対照/recv_pre 現cut例外(本物2+偽物1)", pre["current_exceptions"], 3)
    R.check("FE混在対照/recv_pre アンカー例外(本物2のみ残る)",
            pre["anchor_exceptions"], 2)
    R.check("FE混在対照/recv_pre 帰属(本物=boundary_match,偽物=false_split)",
            pre["attribution"], {"boundary_match": 2, "false_split": 1})

    R.check("FE混在対照/recv_post 現cut例外(本物2+偽物1)", post["current_exceptions"], 3)
    R.check("FE混在対照/recv_post アンカー例外(本物2のみ残る)",
            post["anchor_exceptions"], 2)
    R.check("FE混在対照/recv_post 帰属(本物=boundary_match,偽物=false_split)",
            post["attribution"], {"boundary_match": 2, "false_split": 1})


# --- SEND run系: 境界を崩さず`0F`規則・偶奇規則へ本物の違反を仕込む -------

def build_send_calls() -> list[Row]:
    rows: list[Row] = []
    clock = 10

    def emit(cpu: str, kind: str, port: str, value: str, pc: str) -> None:
        nonlocal clock
        rows.append(Row(clock, cpu, kind, port, value, pc))
        clock += 10

    def clean_run3() -> None:
        emit("main", "OUT", "00FF", "0F", "3700")
        emit("main", "OUT", "00FD", "--", "37F4")
        emit("main", "OUT", "00FD", "--", "3811")
        emit("main", "OUT", "00FD", "--", "37F4")
        emit("main", "IN", "00FC", "--", "3880")

    def ff_violation_run3() -> None:
        # 3要素run(先頭0Fは正しい)だが、継続位置にも本物の0Fを書く。
        # 境界(選択イベントの並び)は clean_run3 と同一。
        emit("main", "OUT", "00FF", "0F", "3700")
        emit("main", "OUT", "00FD", "--", "37F4")
        emit("main", "OUT", "00FF", "0F", "3700")  # 継続への本物の誤書込み
        emit("main", "OUT", "00FD", "--", "3811")
        emit("main", "OUT", "00FD", "--", "37F4")
        emit("main", "IN", "00FC", "--", "3880")

    def parity_violation_run2() -> None:
        # 2要素run(偶数長)の期待末尾pcは"3811"のはずだが、"37F4"のまま終わる。
        # 境界は崩していない。
        emit("main", "OUT", "00FF", "0F", "3700")
        emit("main", "OUT", "00FD", "--", "37F4")
        emit("main", "OUT", "00FD", "--", "37F4")  # 本来なら3811のはず
        emit("main", "IN", "00FC", "--", "3880")

    clean_run3()             # 前置filler(ログ端の巻き添え防止)
    ff_violation_run3()
    ff_violation_run3()
    ff_violation_run3()
    parity_violation_run2()
    parity_violation_run2()
    clean_run3()             # 後置filler(ログ端の巻き添え防止)
    return rows


def send_negative_control(tmp: Path) -> None:
    rows = build_send_calls()
    iolog = tmp / "send-negctl.iolog.txt"
    intlog = tmp / "send-negctl.intlog.txt"
    write_iolog(iolog, rows)
    write_empty_intlog(intlog)
    result = attrib.analyze(iolog, intlog, "send-negctl")
    send = result["send"]

    R.check("SEND陰性対照/現cut 0F例外", send["current"]["ff_exceptions"], 3)
    R.check("SEND陰性対照/アンカー 0F例外(0件に潰れないこと)",
            send["anchor"]["ff_exceptions"], 3)
    R.check("SEND陰性対照/0F帰属(全件境界一致)",
            send["ff_attribution"], {"boundary_match": 3})

    R.check("SEND陰性対照/現cut 偶奇例外", send["current"]["parity_exceptions"], 2)
    R.check("SEND陰性対照/アンカー 偶奇例外(0件に潰れないこと)",
            send["anchor"]["parity_exceptions"], 2)
    R.check("SEND陰性対照/偶奇帰属(全件境界一致)",
            send["parity_attribution"], {"boundary_match": 2})


# --- 正常形(空振り0件の確認: 何も仕込まなければ例外0件) --------------------

def baseline_no_false_positive(tmp: Path) -> None:
    fe_rows = build_fe_calls(5)  # 違反・分割ともに0件
    iolog = tmp / "fe-baseline.iolog.txt"
    intlog = tmp / "fe-baseline.intlog.txt"
    write_iolog(iolog, fe_rows)
    write_empty_intlog(intlog)
    result = attrib.analyze(iolog, intlog, "fe-baseline")
    R.check("FE正常形/recv_pre 例外0件(空振りなし)",
            result["fe"]["recv_pre"]["current_exceptions"], 0)
    R.check("FE正常形/recv_post 例外0件(空振りなし)",
            result["fe"]["recv_post"]["current_exceptions"], 0)

    send_rows: list[Row] = []
    clock = 10

    def emit(cpu: str, kind: str, port: str, value: str, pc: str) -> None:
        nonlocal clock
        send_rows.append(Row(clock, cpu, kind, port, value, pc))
        clock += 10

    for _ in range(4):
        emit("main", "OUT", "00FF", "0F", "3700")
        emit("main", "OUT", "00FD", "--", "37F4")
        emit("main", "OUT", "00FD", "--", "3811")
        emit("main", "OUT", "00FD", "--", "37F4")
        emit("main", "IN", "00FC", "--", "3880")
    iolog2 = tmp / "send-baseline.iolog.txt"
    intlog2 = tmp / "send-baseline.intlog.txt"
    write_iolog(iolog2, send_rows)
    write_empty_intlog(intlog2)
    result2 = attrib.analyze(iolog2, intlog2, "send-baseline")
    R.check("SEND正常形/0F例外0件(空振りなし)",
            result2["send"]["current"]["ff_exceptions"], 0)
    R.check("SEND正常形/偶奇例外0件(空振りなし)",
            result2["send"]["current"]["parity_exceptions"], 0)


def main() -> int:
    fe_classifier_categories()
    send_classifier_categories()
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        fe_negative_control(tmp)
        fe_mixed_control(tmp)
        send_negative_control(tmp)
        baseline_no_false_positive(tmp)

    print()
    if R.failures:
        print(f"NG: {len(R.failures)}件の不一致")
        for f in R.failures:
            print(f"  - {f}")
        return 1
    print("OK: 全項目一致(分類器6カテゴリ×2系統、アンカー陰性対照、空振り0件)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
