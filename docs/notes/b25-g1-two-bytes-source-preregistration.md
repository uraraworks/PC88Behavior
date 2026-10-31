# B25: G1 の直後の 2 バイトを、サブが送っているかを順番で確かめる — 事前登録

記録日: 2026-11-01
位置づけ: [B24](b24-sub-request-15-results.md) の次段。**このノートは測定より先にコミットする。**

OO・SS の `--io-log`（既存を再利用してよい）。実装は `tools/b25_two_bytes.py`。値は読まない。`clock` は main と sub に共通の通し番号である。

main の開始の行（B6 と同じ）から数えて `IN $FC` の番号 3839・3840・3841 の各行について、次を出す。

- `sub OUT $FD` のうち、その行の `clock` より前のものの件数（全体の通し）
- 直前の `sub OUT $FD` の発行元の領域（`lo`/`hi`）
- 直前の `IN $FC` からこの行までの間の `sub OUT $FD` の件数
- 直前の `IN $FC` からこの行までの間の main の `OUT $FF` と `IN $FE` の件数

白リスト: `# 識別子: G1`、`# 走: <name>`、`fc <番号> sub_fd=<N> last=<lo|hi|none> new_fd=<N> out_ff=<N> in_fe=<N>`。

判定: 番号 3840・3841 の `new_fd` が 1 以上なら「サブが送っている」、0 なら「サブは新しく送っておらず、main が読み直している」と腕ごとに書く。原因は書かない。

結果は `measurements/b25-g1-two-bytes-<腕>.txt`、`docs/notes/b25-g1-two-bytes-source-results.md`。
