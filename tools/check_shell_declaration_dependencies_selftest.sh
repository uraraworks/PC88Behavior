#!/usr/bin/env bash
# Bash 3.2 の set -u で壊れる、同一宣言文内の代入間依存の検出力を確認する。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKER="$SCRIPT_DIR/check_shell_declaration_dependencies.py"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0

pass() { echo "OK: $1"; }
ng() { echo "NG: $1" >&2; fail=$((fail + 1)); }

repo_out="$WORK/repo.out"
if python3 "$CHECKER" "$REPO" >"$repo_out" 2>&1 &&
   grep -q '検査完了: OK（.*ファイルを走査、0件）' "$repo_out"; then
  pass "本体検査が実走し、shellスクリプト0件を確認した"
else
  ng "本体検査が未実行、または依存代入を検出した"
  cat "$repo_out" >&2
fi

positive="$WORK/positive.sh"
printf '%s\n' '#!/usr/bin/env bash' 'f() {' \
  '  local a="x" b="$a"' \
  '  declare c="y" d="${c}/z"' \
  '  readonly e="z" f="$e"' '}' > "$positive"
positive_out="$WORK/positive.out"
python3 "$CHECKER" "$positive" >"$positive_out" 2>&1
positive_rc=$?
if [ "$positive_rc" -eq 1 ] &&
   grep -q '検査完了: NG（3件検出）' "$positive_out"; then
  pass "陽性対照の local/declare/readonly 3件を実際に検出した"
else
  ng "陽性対照3件を検出できなかった（rc=${positive_rc}）"
  cat "$positive_out" >&2
fi

bash_major="$(/bin/bash -c 'echo "${BASH_VERSINFO[0]}"')"
bash_minor="$(/bin/bash -c 'echo "${BASH_VERSINFO[1]}"')"
bash_out="$WORK/bash32.out"
/bin/bash -c 'set -u; f(){ local a="x" b="$a"; echo "$b"; }; f' \
  >"$bash_out" 2>&1
bash_rc=$?
if [ "$bash_major" -eq 3 ] && [ "$bash_minor" -eq 2 ]; then
  if [ "$bash_rc" -ne 0 ] && grep -q 'unbound variable' "$bash_out"; then
    pass "macOS Bash 3.2 の実挙動で unbound variable を確認した"
  else
    ng "Bash 3.2 の陽性再現が失敗しなかった（rc=${bash_rc}）"
  fi
else
  echo "SKIP: /bin/bash は3.2ではないため実挙動確認なし（静的陽性対照は実行済み）"
fi

[ "$fail" -eq 0 ] || exit 1
echo "全項目 OK"
