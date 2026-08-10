#!/usr/bin/env python3
"""PC88Behavior: 公式環境での使い捨て測定に関わる共通部品。

2026-08-11、`tools/verify_analyzer_corruption.py` の公式環境モードに実装した
「PC88_REF_ROM_DIR/PC88_REF_DISK_DIR があれば、伏せ字前の生ログを使い捨て
ディレクトリ(リポジトリ外)にその場で測定し、集計だけ持ち帰って生ログは
必ず削除する」という仕組みを、このモジュールへ切り出したもの。

切り出す理由: M6j(バルクモードの起点・終端の特定)でも同じ仕組みが要る。
1ツールに埋めたままだと二重実装になる(CLAUDE.md の趣旨にも反する)ので、
`verify_analyzer_corruption.py` と将来のツール(M6j 用など)の両方が
import して使える形にした。

**これは移動であって機能追加ではない。** 公開する関数の呼び出し方
(引数の綴り・順序)は `verify_analyzer_corruption.py` にあったときの
ものをそのまま保つ。挙動を変えると、切り出し前に公式環境で実走・成功
済みだった経路(docs/notes/m6-sub-proto.md 第5版)が壊れる。

## 安全側の性質(ここは絶対に緩めない)

- 生ログは必ずリポジトリ外の `tempfile.mkdtemp()` に置く
  (`reject_if_in_repo` / `DisposableRawDir`)。
- 使い終わったら例外の有無に関わらず必ず削除する
  (`DisposableRawDir.__exit__`)。
- 生ログのパス・内容を、リポジトリ内のファイルにも標準出力にも書かない。
  この責務はこのモジュール自身は担わない(生ログを直接印字するコードを
  持たない)が、呼び出し側がそれを守れるように、生ログを常に
  `DisposableRawDir` の中だけへ置くAPIにしている。
- 呼び出し側がうっかりリポジトリ配下を指定したら拒否する
  (`reject_if_in_repo`)。

使い方: `tools/verify_analyzer_corruption.py` の公式環境モードを参照。
テスト: `tools/refmeasure_selftest.sh`(このモジュール単体の検査)、
`tools/analyzer_redaction_selftest.sh`(verify 側が正しく使えているかの
結合的な確認)。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class FullMeasurementError(RuntimeError):
    """公式環境モードの測定・解析が失敗したときに使う。"""


def repo_root() -> Path:
    # tools/ の1つ上がリポジトリルート。
    return Path(__file__).resolve().parent.parent


def reject_if_in_repo(path: Path, label: str) -> None:
    """path がリポジトリ配下を指していたら例外で拒否する。

    公式ディスクの実データを含みうる作業ディレクトリは、リポジトリの外に
    置くことが構造上の前提(CLAUDE.md「パスの扱い」)。ここが効いていないと
    「使い捨てのつもりが実はリポジトリ内で、git add一発で持ち出される」
    という事故につながる。呼び出し側が渡す作業ディレクトリにも、
    `DisposableRawDir` が内部で作る使い捨てディレクトリにも同じ関数で
    検査する(経路を分けない)。
    """
    repo = repo_root().resolve()
    p = path.resolve()
    if p == repo or repo in p.parents:
        raise SystemExit(
            f"エラー: {label} がリポジトリ配下を指している ({p})。"
            "公式ディスクの実データを含みうる作業ディレクトリはリポジトリの外に"
            "置くこと(CLAUDE.md「パスの扱い」)。"
        )


def ref_env() -> tuple[str, str] | None:
    """PC88_REF_ROM_DIR/PC88_REF_DISK_DIR の両方が設定されていれば
    (rom_dir, disk_dir) を返す。片方でも未設定なら None を返す。

    呼び出し側はこれで公式環境が使えるかを判定し、None のときは
    `tools/conform_l3.sh` の作法(必要な環境変数と使い方を示して
    終了コード0で SKIP)に揃えたメッセージを自分で出す。
    """
    rom_dir = os.environ.get("PC88_REF_ROM_DIR")
    disk_dir = os.environ.get("PC88_REF_DISK_DIR")
    if not rom_dir or not disk_dir:
        return None
    return rom_dir, disk_dir


class DisposableRawDir:
    """使い捨ての生ログ用作業ディレクトリ。

    tempfile.mkdtemp() でリポジトリの外に作り、reject_if_in_repo で
    確認し、with を抜けるとき(正常終了・例外どちらでも)必ず削除する。
    「例外時も生ログが残らない」という要件を、呼び出し側のtry/finally
    忘れに頼らずこの1箇所に閉じ込めるための実装。
    """

    def __init__(self, prefix: str = "pc88h-refmeasure-") -> None:
        self._prefix = prefix
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix=self._prefix))
        reject_if_in_repo(self.path, "内部作業ディレクトリ(生ログ用)")
        return self.path

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.path is not None:
            shutil.rmtree(self.path, ignore_errors=True)
        return False  # 例外は揉み消さず伝播させる


def discover_frontend_and_core() -> tuple[Path, Path]:
    """tools/conform_l3.sh と同じ場所からフロントエンドとコアを探す。

    綴りを推測しないため、パスの組み立ては conform_l3.sh の
    VENDOR/FRONTEND/CORE の定義に厳密に合わせる。
    """
    repo = repo_root()
    vendor = repo.parent / "vendor" / "quasi88-libretro"
    frontend = repo / "tools" / "harness" / "frontend" / "q88measure"
    if not frontend.exists():
        raise FullMeasurementError(
            f"フロントエンドが無い: {frontend}"
            "（tools/harness/frontend で make を先に実行すること）"
        )
    cores = sorted(vendor.glob("quasi88_libretro.*"))
    if not cores:
        raise FullMeasurementError(
            f"コアが無い: {vendor}/quasi88_libretro.*"
            "（tools/setup_harness.sh を先に実行すること）"
        )
    return frontend, cores[0]


def measure_fresh_raw_log(raw_dir: Path, frames: int) -> tuple[Path, Path]:
    """PC88_REF_ROM_DIR/PC88_REF_DISK_DIR を使い、伏せ字前の生ログ
    (iolog/intlog)を raw_dir にその場で測定して作る。

    呼び出し方(diskA起動、frames の意味、--disk のファイル名)は
    tools/conform_l3.sh の本番区間に厳密に合わせる(綴りを推測しない)。
    生成した生ログをそのまま検証には使うが、コミットも標準出力への
    転記も一切しない(それは呼び出し側の責務)。

    q88measure自身の標準出力/標準エラーには --rom-dir/--disk の私物パスが
    写り込む(main.cの仕様)。これも raw_dir の外へは出さない
    (このプロセスの標準出力・標準エラーには一切転記しない)。
    """
    env = ref_env()
    if env is None:
        raise FullMeasurementError("PC88_REF_ROM_DIR/PC88_REF_DISK_DIR が未設定")
    rom_dir, disk_dir = env

    frontend, core = discover_frontend_and_core()

    disk = Path(disk_dir) / "N88_FE.D88"
    if not disk.is_file():
        raise FullMeasurementError(
            "参照ディスクが無い: (PC88_REF_DISK_DIR)/N88_FE.D88"
        )

    io_log = raw_dir / "live.iolog.txt"
    int_log = raw_dir / "live.intlog.txt"
    q88_stdout = raw_dir / "live.stdout.txt"
    q88_stderr = raw_dir / "live.stderr.txt"

    with open(q88_stdout, "w", encoding="utf-8") as out_f, \
         open(q88_stderr, "w", encoding="utf-8") as err_f:
        proc = subprocess.run(
            [
                str(frontend),
                "--core", str(core),
                "--rom-dir", rom_dir,
                "--disk", str(disk),
                "--frames", str(frames),
                "--io-log", str(io_log),
                "--int-log", str(int_log),
            ],
            stdout=out_f,
            stderr=err_f,
        )

    if proc.returncode != 0 or not io_log.is_file() or not int_log.is_file():
        raise FullMeasurementError(
            f"q88measure の実行に失敗した(終了コード{proc.returncode})。"
            "詳細は使い捨て作業ディレクトリ内の標準出力/標準エラーのログに"
            "あるが、私物のパスが写り込むためこのプロセスの標準出力へは"
            "転記しない。"
        )
    return io_log, int_log
