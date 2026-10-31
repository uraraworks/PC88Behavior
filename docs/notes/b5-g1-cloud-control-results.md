# B5 追補: G1 の境界記録をクラウドの Linux 版コアで再現する — 結果

記録日: 2026-10-31
規則: [goal-b-policy-addendum2-remote-measurement-2026-10-31.md](goal-b-policy-addendum2-remote-measurement-2026-10-31.md) 第4節の対照。

環境: クラウドの実行環境（Ubuntu 24.04・x86_64・4コア）、main 1a85d47 から組んだ `quasi88_libretro.so`。
ROM 9本と G1 の1枚目はプロジェクトのライブラリから複製した。この測定はクラウド側のセッションが行い、
以下は件数と判定の報告を転記したもの（生の出力は誰も開いていない）。

| 確認 | 結果 |
|---|---|
| `library-sha256.txt` による照合 | 10件すべて一致 |
| 公式2走（各 rc=0）の濾過後と `measurements/b1-g1-demand-official-1.txt` | どちらもバイト一致 |
| 公式の走1と走2 | バイト一致 |
| 自作1走（rc=0、`src/build_main_rom.py` のビルド）と `measurements/b5-g1-self-boot-self-1.txt` | バイト一致 |
| 所要 | 公式 2.6秒・2.1秒、自作 2.6秒 |

結論: G1 の境界記録に限れば、Linux 版コアは Mac の記録と区別できない。
他の公式 ROM の検査については、この結果から何も言えない。それぞれ別に確かめる。
