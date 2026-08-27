#!/usr/bin/env bash
# conform_l3.sh と単独selftestで共有する期待値照合・故障注入。
# 呼出側は HASH, WORK と ok/ng を定義すること。

run_conformance() {
  local iolog="$1" expected="$2" label="$3"
  local rc=0 rows=0
  local name cpu port kind count sha out a_count a_sha

  if [ ! -r "$expected" ]; then
    ng "[$label] 期待値を読めない: $expected"
    return 1
  fi

  while IFS=$'\t' read -r name cpu port kind count sha; do
    [ -z "${name:-}" ] && continue
    case "$name" in \#*) continue ;; esac
    rows=$((rows + 1))

    if out="$(python3 "$HASH" "$iolog" --cpu "$cpu" --port "$port" --kind "$kind" 2>"$WORK/err.$name")"; then
      a_count="$(printf '%s\n' "$out" | awk -F'\t' '$1=="count"{print $2}')"
      a_sha="$(printf '%s\n' "$out" | awk -F'\t' '$1=="sha256"{print $2}')"
    else
      ng "[$label] ${name}: 抽出に失敗（${cpu}/${kind}/${port}）"
      sed 's/^/       /' "$WORK/err.$name"
      rc=1
      continue
    fi

    if [ "$a_count" != "$count" ]; then
      ng "[$label] ${name}: 件数不一致（期待 ${count} 件 ／ 実測 ${a_count} 件。ハッシュ以前に検出）"
      rc=1
    elif [ "$a_sha" != "$sha" ]; then
      ng "[$label] ${name}: 件数(${a_count}件)は一致するがSHA-256が不一致"
      rc=1
    else
      ok "[$label] ${name}: 件数(${a_count})・SHA-256とも一致"
    fi
  done < "$expected"

  if [ "$rows" -eq 0 ]; then
    ng "[$label] 期待値のデータ行が0件"
    rc=1
  fi
  return "$rc"
}

entry_expected_fault_selftest() {
  local iolog="$1" expected="$2" label="$3"
  local bad_sha bad_count empty rows
  local rc=0

  bad_sha="$(mktemp "$WORK/entry-expected.bad-sha.XXXXXX")" || return 1
  bad_count="$(mktemp "$WORK/entry-expected.bad-count.XXXXXX")" || return 1
  empty="$(mktemp "$WORK/entry-expected.empty.XXXXXX")" || return 1

  rows="$(awk '!/^#/ && NF {n++} END {print n+0}' "$expected")" || return 1
  if [ "$rows" -eq 0 ]; then
    ng "${label}: 元の期待値のデータ行が0件"
    return 1
  fi

  if ! awk 'BEGIN{FS=OFS="\t"} /^#/ || NF==0 {print; next}
       { sha=$6; last=substr(sha,length(sha),1)
         $6=substr(sha,1,length(sha)-1) (last=="0"?"f":"0"); print }' \
      "$expected" > "$bad_sha"; then
    ng "${label}: SHA-256故障コピーを生成できない"
    return 1
  fi
  if [ "$(awk '!/^#/ && NF {n++} END {print n+0}' "$bad_sha")" -eq 0 ]; then
    ng "${label}: SHA-256故障コピーのデータ行が0件"
    return 1
  fi
  if run_conformance "$iolog" "$bad_sha" "${label}-hash故障" >/dev/null 2>&1; then
    ng "${label}: 壊したSHA-256が一致してしまった"
    rc=1
  else
    ok "${label}: SHA-256を壊した期待値コピーを不一致検出"
  fi

  if ! awk 'BEGIN{FS=OFS="\t"} /^#/ || NF==0 {print; next}
      {$5=$5+1; print}' "$expected" > "$bad_count"; then
    ng "${label}: 件数故障コピーを生成できない"
    return 1
  fi
  if [ "$(awk '!/^#/ && NF {n++} END {print n+0}' "$bad_count")" -eq 0 ]; then
    ng "${label}: 件数故障コピーのデータ行が0件"
    return 1
  fi
  if run_conformance "$iolog" "$bad_count" "${label}-件数故障" >/dev/null 2>&1; then
    ng "${label}: 壊した件数が一致してしまった"
    rc=1
  else
    ok "${label}: 件数を壊した期待値コピーを不一致検出"
  fi

  if ! : > "$empty"; then
    ng "${label}: 空期待値コピーを生成できない"
    return 1
  fi
  if run_conformance "$iolog" "$empty" "${label}-空期待値故障" >/dev/null 2>&1; then
    ng "${label}: 期待値0行が一致してしまった"
    rc=1
  else
    ok "${label}: 期待値0行を不一致検出"
  fi
  return "$rc"
}
