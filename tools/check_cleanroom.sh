#!/usr/bin/env bash
# クリーンルーム防御が実際に効いている状態かを検査する。
#
# 規律は「書いてある」だけでは効かない。以下を機械的に確かめる:
#   1. private/ が git から遮断されている（実際にダミーを置いて確認）
#   2. リポジトリの外に置いた ROM 系ファイルも遮断される
#   3. 追跡ファイルに ROM 由来らしきバイナリが混入していない
#   4. permission 設定が実効位置（cwd 側）から見えている
#   5. 実効側と実体（このリポジトリ）が同じ内容である
#
# 使い方: tools/check_cleanroom.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

fail=0
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()   { printf '  \033[31mNG\033[0m   %s\n' "$1"; fail=$((fail+1)); }
info() { printf '  --   %s\n' "$1"; }

echo "clean-room check: $REPO"

WORK_CR="$(mktemp -d)"
trap 'rm -rf "$WORK_CR"' EXIT

# --- 1. private/ の遮断 -------------------------------------------------
mkdir -p private
probe="private/.__probe__"
: > "$probe"
if git check-ignore -q "$probe"; then ok "private/ は git から遮断されている"
else ng "private/ が git に見えている（.gitignore を確認）"; fi
rm -f "$probe"

# --- 2. private/ の外に置いた ROM 系も遮断されるか ----------------------
stray=".__probe__.rom"
: > "$stray"
if git check-ignore -q "$stray"; then ok "リポジトリ直下の *.rom も遮断される"
else ng "*.rom が遮断されていない"; fi
rm -f "$stray"

# --- 3. 追跡ファイルへのバイナリ混入 ------------------------------------
# ROM 由来のバイト列は必ずバイナリになる。テキストしか追跡していないはず。
# 空ファイル(.gitkeep 等)は対象外。NUL バイトを含むものをバイナリとみなす。
#
# 例外: measurements/*.gz は伏せ字適用後に gzip したテキストログであり、
# バイナリ形式そのものが目的（2026-08-10、docs/notes/disclosure-2026-08-10.md）。
# gzip という「バイナリであること」自体は問題ではなく、中身が伏せ字済みかが
# 問題なので、ここでは除外し、下の 7. で内容を個別に検査する。
binaries=""
while IFS= read -r f; do
  [ -s "$f" ] || continue
  case "$f" in
    measurements/*.gz) continue ;;
  esac
  # シェル文字列に NUL は入らないので grep のパターンには書けない。
  # NUL を除去した長さが元と違えば NUL を含む = バイナリ。
  if [ "$(LC_ALL=C tr -d '\000' < "$f" | wc -c)" -ne "$(wc -c < "$f")" ]; then
    binaries="$binaries $f"
  fi
done < <(git ls-files)
if [ -z "$binaries" ]; then ok "追跡ファイルにバイナリの混入なし（measurements/*.gz を除く。7.で個別検査）"
else ng "バイナリが追跡されている:"; printf '       %s\n' $binaries; fi

# --- 4/5. permission 設定の実体と実効位置 -------------------------------
src="$REPO/.claude/settings.json"
eff="$(cd "$REPO/.." && pwd)/.claude/settings.json"   # cwd 側 = PC88/.claude/

if [ -f "$src" ]; then ok "permission 設定の実体がある（公開repo側）"
else ng "permission 設定の実体が無い: $src"; fi

if [ -e "$eff" ]; then
  if [ -L "$eff" ]; then info "実効側は symlink → $(readlink "$eff")"; fi
  if cmp -s "$src" "$eff"; then ok "実効側 (cwd) と実体の内容が一致している"
  else ng "実効側と実体の内容がずれている: $eff"; fi
else
  ng "実効側に permission 設定が無い: ${eff}（cwd が PC88 だと実体だけでは読まれない）"
fi

# --- 6. 計測ハーネスが禁止された能力を持っていないか ----------------------
# 「使わない」ではなく「持っていない」を検査する。
harness="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
if [ -d "$harness" ]; then
  for f in src/z80-debug.c src/LIBRETRO/pseudo_bios.h; do
    if [ -e "$harness/$f" ]; then ng "ハーネスに $f が存在する（setup_harness.sh が消すはず）"
    else ok "ハーネスに $f は存在しない"; fi
  done
  lib="$(ls "$harness"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
  if [ -n "$lib" ]; then
    # `nm | grep -q` は使わない。pipefail 下では grep -q の早期終了が
    # nm を SIGPIPE で殺し、判定が反転する（setup_harness.sh の注記参照）。
    syms="$(nm "$lib" 2>/dev/null || true)"
    case "$syms" in
      *pbios*) ng "ビルド成果物に疑似BIOSのシンボルがある" ;;
      *)       ok "ビルド成果物に疑似BIOSのシンボルなし" ;;
    esac
    case "$syms" in
      *retro_q88h_trace*) ok "ビルド成果物に計測フックのシンボルあり" ;;
      *)                  ng "ビルド成果物に計測フックのシンボルが無い" ;;
    esac
  fi
else
  info "ハーネス未取得のためスキップ（tools/setup_harness.sh）"
fi

# --- 7. measurements/*.iolog.txt(.gz) のデータポートが伏せ字済みか -------
# CLAUDE.md 禁止事項5（2026-08-10追加。docs/notes/disclosure-2026-08-10.md）。
# 対象: 追跡中の measurements/*.iolog.txt* すべて（.gz可）。
#   (a) 非.gzの *.iolog.txt が追跡されていたら即NG（gzip忘れ）
#   (b) $FB/$FC/$FD (main/sub, IN/OUT) の value 列に "--" 以外の値が
#       1件でも残っていたら NG（伏せ字漏れ）
#
# tools/redact_iolog.py を検査に流用しない。あのツールは「伏せた記録」の
# 節（FOOTER_MARKER）が既にあると即座に無変更を返す（冪等性のため）。
# もし伏せた後に何らかの理由で行が1件でも復元されても、その仕組みだと
# 検出できない（実際に試して確認した——後述「検出力の自己検査」参照）。
# ここでは冪等性の仕組みを経由せず、全行を独立に読んで判定する。
plain=""
while IFS= read -r f; do
  case "$f" in
    measurements/*.iolog.txt) plain="$plain $f" ;;
  esac
done < <(git ls-files measurements)
if [ -n "$plain" ]; then
  ng "gzip されていない .iolog.txt が追跡されている:"; printf '       %s\n' $plain
else
  ok "追跡中の .iolog.txt はすべて .gz 化されている"
fi

cat > "$WORK_CR/scan_masked.py" <<'PYEOF'
import gzip, sys

TARGET = {"00FB", "00FC", "00FD"}

bad = []
for path in [l.strip() for l in sys.stdin if l.strip()]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        bad.append(f"{path}(読めない:{e})")
        continue
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        fields = s.split()
        if len(fields) == 7:
            seq_s, frame_s, cpu, kind, port, value, pc = fields
        elif len(fields) == 8:
            seq_s, clock_s, frame_s, cpu, kind, port, value, pc = fields
        else:
            continue
        if kind not in ("IN", "OUT") or cpu not in ("main", "sub"):
            continue
        try:
            int(seq_s)
        except ValueError:
            continue
        port_norm = port.upper().zfill(4)
        if port_norm in TARGET and value != "--":
            bad.append(f"{path}({cpu}/{kind}/{port_norm}=masked外)")
            break
for b in bad:
    print(b)
PYEOF
unmasked="$(git ls-files measurements | grep '\.iolog\.txt\.gz$' | python3 "$WORK_CR/scan_masked.py")"
if [ -n "$unmasked" ]; then
  ng "データポート(\$FB/\$FC/\$FD)の値が伏せ字されていないファイルがある:"
  printf '       %s\n' $unmasked
else
  ok "追跡中の iolog.txt.gz は全てデータポートの値が伏せ字済み"
fi

# --- 8. 追跡ファイルに50MB超のものが無いか --------------------------------
# docs/PLAN.md「運用上の課題」（m6e-diskB-boot*が72MB超のまま公開された）
# の再発防止。GitHubの推奨上限50MBを基準にする。
big=""
while IFS= read -r f; do
  [ -f "$f" ] || continue
  sz="$(wc -c < "$f" | tr -d ' ')"
  if [ "$sz" -gt $((50*1024*1024)) ]; then
    big="$big $f(${sz}B)"
  fi
done < <(git ls-files)
if [ -z "$big" ]; then ok "追跡ファイルに50MB超のものは無い"
else ng "50MB超の追跡ファイルがある:"; printf '       %s\n' $big; fi

# --- 9. 変数展開直後に非ASCII文字が来ていないか(UTF-8ロケールでの識別子誤認) -
# 背景: UTF-8ロケールのbashは識別子をマルチバイト単位で解釈できてしまうため、
# 「$port）」のように $var の直後に全角文字が続くと「port）」までが変数名だと
# 読まれ、$port は未定義扱いになる。set -u があれば即死(実際に
# tools/conform_l3.sh がこれで自己検査の途中で死に、以降の本体が
# 一度も走っていなかった)、無ければ空文字列に化けて黙って誤動作する。
# これまでの回帰確認は全てCロケールで行っており(Cロケールは0x80以上を
# 識別子に含めないため無症状)、UTF-8ロケールでは一度も検出されていなかった。
#
# 判定はヒューリスティック: 行頭からその出現位置までの未エスケープ `'` の
# 個数が奇数ならシングルクオート内(展開されない)とみなして除外する。
# 複数行文字列やコマンド内のネストまでは追えないため完全ではない。
# 誤検出したときは、握りつぶさずに対象行の末尾に
# `# cleanroom-lint:ignore` を付けて除外理由をコメントで書くこと。
# コメント行(先頭が # のもの)は無条件で除外する。
cat > "$WORK_CR/scan_var_ascii.py" <<'PYEOF'
import re
import sys

PATTERN = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)')

def scan(path, lines):
    hits = []
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip('\n')
        if line.rstrip().endswith('# cleanroom-lint:ignore'):
            continue
        if line.lstrip().startswith('#'):
            continue
        for m in PATTERN.finditer(line):
            end = m.end()
            if end >= len(line):
                continue
            nxt = line[end]
            if ord(nxt) < 0x80:
                continue
            before = line[:m.start()]
            if before.count("'") % 2 == 1:
                continue  # シングルクオート内と推定(ヒューリスティック)
            hits.append((i, line.strip(), m.group(0), nxt))
    return hits

bad = False
for path in sys.argv[1:]:
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()
    except OSError as e:
        print(f"{path}: 読めない({e})")
        bad = True
        continue
    for lineno, line, var, nxt in scan(path, lines):
        print(f"{path}:{lineno}: {var} の直後が非ASCII文字'{nxt}' -> {line}")
        bad = True

sys.exit(1 if bad else 0)
PYEOF
sh_file_list=()
while IFS= read -r f; do sh_file_list+=("$f"); done < <(git ls-files '*.sh')
if [ "${#sh_file_list[@]}" -gt 0 ]; then
  if varhits="$(python3 "$WORK_CR/scan_var_ascii.py" "${sh_file_list[@]}" 2>&1)"; then
    ok "追跡中の *.sh に変数展開直後の非ASCII文字は無い"
  else
    ng "変数展開直後に非ASCII文字がある(UTF-8ロケールで識別子として吸われ誤動作する恐れ):"
    printf '       %s\n' "$varhits"
  fi
fi

echo
if [ "$fail" -eq 0 ]; then echo "全項目 OK"; else echo "$fail 件 NG"; fi
exit "$fail"
