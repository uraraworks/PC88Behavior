#!/usr/bin/env python3
"""PC88Behavior: l4-c5 代表プログラム集 — 打鍵計画の組み立て道具。

事前登録 `docs/notes/l4-c5-representative-programs-conformance-scene-
preregistration.md`（`2837926`）「腕」節・「P8（INPUT）の打鍵タイミング」
節・G9（打鍵到達確認）節どおりに `tests/programs/*.bas` の1本を読み、
打鍵文字列と`--vram-dump`を置くべきフレーム番号を組み立てる。

## 手順（2026-09-16改定・追補2: `new`の直後にも`cls`を挟む）

試走で、行数の多いプログラム（`p02`・`p03`・`p06`）は、プログラムの
入力そのもの（`new`〜各行の打鍵）だけで画面が下へ流れ（スクロール）、
`run`を打った行の位置が一意に定まらない（`tools/l4_program_conform_
record.py`が`ok_row_not_found`と正しく判別した）ことが分かった。

対策その1（1回目の改定）: プログラムを打ち終えた直後に`cls`を打ち、
その`Ok`が出た後の写しを「写し(前)」として使う手順に変えた。`cls`は
画面を消してカーソルを先頭（絶対行0）へ戻すため（`l4-s5f`のF1・F10で
確認済み）、以後`run`を打った行・出力・`Ok`はいずれも先頭付近の低い
絶対行に収まり、プログラムの行数に左右されなくなった。

対策その2（追補2）: 1回目の改定後も、G9（打鍵到達確認）自体は`new`〜
プログラムの行の打鍵を、起動時のバナーが残る絶対行6以降を前提に数え
ていた。行数の多いプログラム（特に`p03`、19行）では、プログラムの
入力そのものが`cls`（1回目の）より前に画面をスクロールさせ、初めの
方の行が除外対象の絶対行0-5へ押し出されてしまい、G9が正しく数えられ
ない場合があった（`p03`で実際に不一致が起きた。`ok_row_not_found`とは
別の問題として報告済み）。

対策として、**`new`の直後にも`cls`を打ち、バナーを消してから
プログラムの行を打ち始める**。バナーが最初から画面に無ければ、
プログラムの行の入力そのもので画面がスクロールする前に、行番号で
始まる行の数を（バナーの影響を受けずに）正しく数えられる。G9の数え方
も、`最下行(19、ファンクションキー表示行)を除く画面全体`で「行番号で
始まる行」（`tools/l4_list_classify.py`の`_classify_row`と同じ判定基準
——先頭の空白を除いた最初の文字が数字で、全セルが表示可能ASCII）の件数
を数える形に変えた（旧版の「非空白行数がexpected_line_count+2」という
数え方は、`Ok`行の数・位置に関する前提を含んでいたため、より頑丈な
「行番号で始まる行」基準に置き換えた）。

**`run`の打鍵は、2回目の`cls`（プログラムの行の後）の`Ok`が出たことを
確認した時点（`cls_dump_frame`）より後にしか始めない。** 最初の実装は
`new`〜`cls`〜`run`を1つの`--type`文字列として連続で打鍵し、
`cls_dump_frame`はその内部の任意のフレームへの単なる写し取得点として
扱っていたが、それでは`run`の打鍵が`cls`の直後（`cls`の`Ok`を待たずに）
始まってしまい、`cls_dump_frame`時点の写しに`run`の打鍵・出力までもが
写り込み、`cls`前後の差分が「変化なし」になってしまう不具合が公式ROM
での試走で見つかった（`tools/l4_program_conform_record.py`が
`no_changes`と正しく検出した）。そこで`l4-s5d`のD12・`l4-s5e`のE1/E2と
同じやり方——`--type-at`で区切った別々の`--type`区間にする——に直し、
`run`（P8はさらに入力値）の区間の`--type-at`を`cls_dump_frame`
（またはP8のプロンプト確認フレーム）に明示的に合わせる。1回目の`cls`
（`new`の直後）は、G9の写しを取る前の同じ区間内で続けて打つため
（`run`のときのような「待ってから続ける」必要は無い——`new`の`Ok`も
1回目の`cls`自身も、G9のサンプリング時点までに十分な時間があるため）、
専用の区間分けは不要。

## 打鍵の区間（P1〜P7、2区間）

```
区間1 (type_at=700):  new\ncls\n<プログラムの各行>\ncls\n
区間2 (type_at=cls_dump_frame): run\n
```

（G9の写しは区間1の途中、`<プログラムの各行>`を打ち終えた時点
`g9_check_frame`で取る。`cls\n`〔2回目〕はその後に続けて打つ）

## フレームの決め方

1文字あたり `hold+gap=8` フレーム（`l4-s5a` 以来の段階5の前例どおり）。
`type_at` の基準は `700`（起動settle `--type-at 300 --type '\n'` の後）。

- `prefix` = `"new\ncls\n"` + プログラムの各行を `\n` 区切りで連結した
  もの + `"\n"`（＝2回目の`cls` を打つ直前までの打鍵文字列）
- `g9_check_frame` = `700 + 8 * len(prefix)`
  （プログラムを打ち終えた瞬間。G9〔打鍵到達確認〕は、ここで取った
  写しに対して行う——2回目の`cls`より前、`run`より前）
- `segment1` = `prefix` + `"cls\n"`（2回目の`cls`）
- `cls_line_end` = `700 + 8 * len(segment1)`
  （2回目の`cls\n`の最後の文字が打鍵される瞬間）
- `cls_dump_frame` = `cls_line_end + 300`
  （`cls`の`Ok`が出るまでの余裕。既存の前例——`l4-s5a`以来の
  `dump(k)=line_end(k)+300`——をそのまま流用する。この写しを
  「写し(前)」として`tools/l4_program_conform_record.py`に渡す）
- `segment2` = `"run\n"`。`--type-at cls_dump_frame`で区間1とは別に打つ
- `line_end2` = `cls_dump_frame + 8 * len(segment2)`
- `dump_final` = `line_end2 + RUN_WAIT_FRAMES`
- `run_total_frames` = `dump_final + 200`

P8（`INPUT`を含む）は、`run\n`の後さらにプロンプト確認・入力値の区間が
続く（`l4-s5e` のE1・E2と同じ考え方。事前登録の式の`n1`は本ノートの
`segment1+segment2`の合計文字数に相当する）。

## `run`（P8は入力値も）の後の待ち（2026-09-16 二度目の改定、追補4）

自作ROMでP2（`p02_primes.bas`）が`ok_row_not_found`になった原因は
実装の誤りではなく、**自作のインタプリタが公式より遅く、`run`の後の
待ち（旧`+300`フレーム）の中に実行が終わらなかった**ことだった
（別担当が観測、事前登録追補4で扱う予定）。適合で比べるのは実行が
終わった後の画面であって速さではないため、`run`の後（P8はさらに
入力値の後）の待ちを**`RUN_WAIT_FRAMES`（全腕一律`3000`フレーム）**
へ延ばす。**公式・自作で同じ値を使う**（速さの違いを比較対象にしない
ための延長であり、一方だけ延ばすと「遅いから通す」ことになり適合の
意味が無くなる）。値は`RUN_WAIT_FRAMES`定数1か所で管理する。

- 変わるのは`dump_final`（P1〜P7）・`dump_prompt`と`dump_final`
  （P8。`run`の後＝プロンプト確認前の待ち、入力値の後＝最終確認前の
  待ちの両方）だけ。`new`直後・プログラムの行の後の`cls`の待ち
  （`cls_dump_frame`、`+300`）は変えない（`cls`の応答は元々速く、
  今回の原因とは無関係なため）。
- 判定（比べるもの）自体は変えない。`dump_final`時点で`Ok`が出て
  いなければ引き続き`ok_row_not_found`等で`gate_failed`になる
  （待ちを延ばすだけで、出なかったものを出たことにはしない）。

### 観察用の追加の写し（`observation_frames`。判定とは別）

`run`（P8は入力値）を打ってから`dump_final`までの待ちの中で、実際に
何フレームで`Ok`が現れたか（＝実行にかかったおおよその時間）を、
判定に使わない**観察**として別途出せるように、待ちの区間へ均等割りの
サンプル点`observation_frames`（`OBSERVATION_SAMPLE_COUNT`個）を追加
した。`tools/l4_program_run.sh`はこの各フレームでも`--vram-dump`を
追加で取り、`tools/l4_program_conform_record.py`の記録器（写し(前)との
差分）を使って「最初に`status=ok`になったサンプルのフレーム番号」を
`approx_ok_frame`として標準出力へ出す（見つからなければ`unknown`）。
出すのはフレーム番号（整数）だけで、画面の文字は一切出さない
（CLAUDE.md禁止事項7）。サンプル間隔ぶんの誤差を含む近似値であり、
判定（`conform`/`not_conform`/`gate_failed`）には一切使わない。

## 使い方

```
python3 tools/l4_program_typeplan.py --bas tests/programs/p01_kuku.bas
python3 tools/l4_program_typeplan.py --bas tests/programs/p08_input_calc.bas --input 5,3
```

出力はJSON 1行（安全な計画情報のみ。画面本文・実行結果は含まない）。
`type_segments`に`[type_at, text]`の並びを含む——`tools/l4_program_run.sh`
はこれをそのまま複数の`--type-at`/`--type`引数の組に展開する。
自分で書いた`tests/programs/`のソースそのものであり、公式ROM由来の
データではないため、禁止事項7（画面本文）の対象外——打つ前の入力
そのものであって、実行結果の画面ではない。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l4_vram_probe  # noqa: E402

TYPE_AT_BASE = 700
FRAMES_PER_CHAR = 8
SETTLE_TYPE_AT = 300
CLS_SEGMENT = "cls\n"
RUN_SEGMENT = "run\n"

# `run`（P8はさらに入力値）を打った後、判定に使う写しを取るまでの待ち。
# 追補4: 自作ROMのインタプリタが公式より遅く、旧`+300`フレームでは
# 実行が終わらない(=`Ok`が出る前に写しを取ってしまう)腕があったため、
# 全腕一律でここを延ばす。**速さは比較対象にしない**——公式・自作の
# 両方に同じ値を使う（tools/conform_l4.shのPROGRAM場面も本定数を
# 唯一の出所として使う。書き換えるならここ1か所でよい）。
RUN_WAIT_FRAMES = 3000

# 観察用(observation_frames)のサンプル点の個数。判定には使わない。
OBSERVATION_SAMPLE_COUNT = 6


def compute_observation_frames(start: int, end: int, count: int = OBSERVATION_SAMPLE_COUNT) -> "list[int]":
    """`start`(runまたは入力値を打ち終えた直後)から`end`(dump_final)の
    間を`count`個に均等割りしたサンプルフレームを返す(端点は含めない)。
    判定には使わない観察用——`Ok`がおおよそ何フレームで現れたかを、
    tools/l4_program_run.shが写しを追加で取って近似するために使う。"""
    if count <= 0 or end <= start + 1:
        return []
    frames = []
    for i in range(1, count + 1):
        f = start + (end - start) * i // (count + 1)
        if start < f < end:
            frames.append(f)
    return sorted(set(frames))


def read_program_lines(bas_path: str) -> "list[str]":
    """`.bas`ファイルを読み、空行を除いた各行(改行なし)を返す。"""
    lines: "list[str]" = []
    with open(bas_path, "r", encoding="ascii") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if line.strip() == "":
                continue
            lines.append(line)
    return lines


def frame_plan(lines: "list[str]") -> dict:
    """INPUTを含まない腕(P1〜P7)の打鍵計画。2区間(new〜cls〜行〜cls / run)。"""
    prefix = "new\n" + CLS_SEGMENT + "\n".join(lines) + "\n"
    g9_check_frame = TYPE_AT_BASE + FRAMES_PER_CHAR * len(prefix)

    segment1 = prefix + CLS_SEGMENT
    cls_line_end = TYPE_AT_BASE + FRAMES_PER_CHAR * len(segment1)
    cls_dump_frame = cls_line_end + 300

    segment2 = RUN_SEGMENT
    line_end2 = cls_dump_frame + FRAMES_PER_CHAR * len(segment2)
    dump_final = line_end2 + RUN_WAIT_FRAMES
    run_total_frames = dump_final + 200
    observation_frames = compute_observation_frames(line_end2, dump_final)

    return {
        "num_lines": len(lines),
        "prefix_char_count": len(prefix),
        "settle_type_at": SETTLE_TYPE_AT,
        "type_at": TYPE_AT_BASE,
        "g9_check_frame": g9_check_frame,
        "segment1": segment1,
        "cls_line_end": cls_line_end,
        "cls_dump_frame": cls_dump_frame,
        "dump_before_frame": cls_dump_frame,
        "segment2_type_at": cls_dump_frame,
        "segment2": segment2,
        "line_end2": line_end2,
        "run_wait_frames": RUN_WAIT_FRAMES,
        "dump_after_frame": dump_final,
        "run_total_frames": run_total_frames,
        "observation_frames": observation_frames,
        "type_segments": [[TYPE_AT_BASE, segment1], [cls_dump_frame, segment2]],
    }


def input_frame_plan(lines: "list[str]", input_value: str) -> dict:
    """INPUTを含む腕(P8)の打鍵計画。3区間(new〜cls〜行〜cls / run / 入力値)。
    `run`の後のプロンプト確認は`l4-s5e`のE1・E2と同じ考え方
    (`+300`フレームの余裕を`--nonblank-summary-rows`で確認)。"""
    prefix = "new\n" + CLS_SEGMENT + "\n".join(lines) + "\n"
    g9_check_frame = TYPE_AT_BASE + FRAMES_PER_CHAR * len(prefix)

    segment1 = prefix + CLS_SEGMENT
    cls_line_end = TYPE_AT_BASE + FRAMES_PER_CHAR * len(segment1)
    cls_dump_frame = cls_line_end + 300

    segment2 = RUN_SEGMENT
    line_end2 = cls_dump_frame + FRAMES_PER_CHAR * len(segment2)
    dump_prompt = line_end2 + RUN_WAIT_FRAMES

    type_at3 = dump_prompt
    segment3 = input_value + "\n"
    n3 = len(segment3)
    line_end3 = type_at3 + FRAMES_PER_CHAR * n3
    dump_final = line_end3 + RUN_WAIT_FRAMES
    run_total_frames = dump_final + 200
    observation_frames = compute_observation_frames(line_end3, dump_final)

    return {
        "num_lines": len(lines),
        "prefix_char_count": len(prefix),
        "settle_type_at": SETTLE_TYPE_AT,
        "type_at": TYPE_AT_BASE,
        "g9_check_frame": g9_check_frame,
        "segment1": segment1,
        "cls_line_end": cls_line_end,
        "cls_dump_frame": cls_dump_frame,
        "dump_before_frame": cls_dump_frame,
        "segment2_type_at": cls_dump_frame,
        "segment2": segment2,
        "line_end2": line_end2,
        "dump_prompt_frame": dump_prompt,
        "type_at2": dump_prompt,  # 旧フィールド名(l4-s5e踏襲)。type_at3と同義。
        "segment3_type_at": type_at3,
        "segment3": segment3,
        "input_type_string": segment3,
        "input_char_count": n3,
        "line_end3": line_end3,
        "run_wait_frames": RUN_WAIT_FRAMES,
        "dump_final_frame": dump_final,
        "run_total_frames": run_total_frames,
        "observation_frames": observation_frames,
        "type_segments": [
            [TYPE_AT_BASE, segment1],
            [cls_dump_frame, segment2],
            [type_at3, segment3],
        ],
    }


def check_keystroke_arrival(dump_path: str, expected_line_count: int, exclude_rows: "set[int] | None" = None) -> dict:
    """G9(打鍵の到達確認、追補2で改定)。`new`の直後に`cls`を打ってバナー
    を消した後、プログラムの行を打ち終えた時点の写し(`g9_check_frame`)
    を、最下行(19、ファンクションキー表示行)を除く画面全体について、
    「行番号で始まる行」（`tools/l4_list_classify.py`の`_classify_row`
    と同じ判定基準——先頭の空白を除いた最初の文字が数字0-9で、行の
    全80セルが表示可能ASCII——`d330dd2`。二重実装せずそのままimportして
    使う）の件数で数える。文字コードそのものは一切出さない（真偽判定
    にしか使わない）。

    1回目の`cls`（`new`の直後）でバナーを消してあるため、この時点で
    「行番号で始まる行」に分類されるのはプログラムの各行の入力エコー
    だけのはずで、その件数がプログラムの行数と一致するかを見る
    （`Ok`行・`new`/`cls`自身の入力エコーは行番号で始まらないため、
    自然に数えから除かれる）。
    """
    if exclude_rows is None:
        exclude_rows = {19}
    import l4_list_classify

    data = l4_vram_probe.load_vram_dump(dump_path)
    char_rows = l4_vram_probe.char_rows(data)
    actual = 0
    for r in range(l4_vram_probe.ROWS):
        if r in exclude_rows:
            continue
        if l4_list_classify._classify_row(char_rows[r]):
            actual += 1
    return {
        "expected_line_count": expected_line_count,
        "actual_line_count": actual,
        "arrived": actual == expected_line_count,
    }


def check_keystroke_arrival_by_list(before_path: str, after_path: str, expected_line_count: int) -> dict:
    """G9の任意の二重確認(事前登録どおり「使えるなら」)。`list`を打った
    結果を`tools/l4_list_classify.py`（`d330dd2`）で分類し、`list_line`
    に分類された行数がプログラムの行数と一致するかを見る。自作ROM側の
    プログラムモードがまだ`LIST`を実装していない段階では、この関数は
    使わず、`check_keystroke_arrival`の件数確認だけで足りるとする
    （事前登録どおり）。"""
    import l4_list_classify

    record = l4_list_classify.classify(before_path, after_path)
    if record.get("classification") != "ok":
        return {"list_checked": False, "reason": record.get("classification")}
    list_line_count = sum(1 for l in record["lines"] if l["classification"] == "list_line")
    return {
        "list_checked": True,
        "expected_line_count": expected_line_count,
        "actual_list_line_count": list_line_count,
        "arrived": list_line_count == expected_line_count,
    }


def check_output_fits_screen(ok_relative_row: int, max_screen_rows: int = 20) -> dict:
    """G10(出力が画面に収まっていること)。`origin_row`(`run`を打った行)
    から`ok_row`(`Ok`の行)までの行数(=ok_relative_row+1)が、画面の行数
    (既定表示20行、`docs/spec/l3-main.md`第5節)を超えていないかを見る。
    """
    span = ok_relative_row + 1
    return {
        "span_rows": span,
        "max_screen_rows": max_screen_rows,
        "fits": span <= max_screen_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", required=True, help="tests/programs/*.bas のパス")
    ap.add_argument("--input", default=None, help="INPUTに打つ値(例: 5,3)。指定したP8向けの計画を返す")
    args = ap.parse_args()

    lines = read_program_lines(args.bas)
    if args.input is not None:
        plan = input_frame_plan(lines, args.input)
    else:
        plan = frame_plan(lines)
    plan["bas_path"] = args.bas
    print(json.dumps(plan, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
