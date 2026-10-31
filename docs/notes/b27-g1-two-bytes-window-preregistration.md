# B27: G1 の直後の 2 バイトの前後の、ポートの並びを値を見ずに見る — 事前登録

記録日: 2026-11-01
位置づけ: [B26](b26-sub-two-bytes-probe-results.md) の次段。**このノートは測定より先にコミットする。**

OO・SS の `--io-log`（既存を再利用してよい）。実装は `tools/b27_window.py`。`clock` で main と sub を 1 本に並べる。

窓は main の開始の行（B6 と同じ）から数えて `IN $FC` 番号 3839 の行から番号 3841 の行まで。窓の中の各行を、CPU・方向・ポート・領域（main は `0x8000`、sub は `0x2000` で分ける）に変え、連続する同じものを畳む。

白リスト: `# 識別子: G1`、`# 走: <name>`、`seq <main|sub> <IN|OUT> <4桁16進> <lo|hi> <回数>`。値・PC の番地・clock は出さない。

判定: main の `OUT $FD` が窓の中にあるか、ある場合はどの `IN $FC` の間か。その前後で sub が `IN $FC` を何回読むか。OO と SS の並びの最初に違う位置をそのまま書く。原因は書かない。

結果は `measurements/b27-g1-window-<腕>.txt`、`docs/notes/b27-g1-two-bytes-window-results.md`。
