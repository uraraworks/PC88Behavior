#!/usr/bin/env python3
"""M6r: batch2/5 が SPECIFY か SEEK かを、$FA(MSR) の下位4bit(Seek Busy)で判別する。
対照群: batch3/4/6/7 (RECALIBRATE, 一意に同定済み)。

方法:
  1. m6qと同じ手法で起動時FDC初期化区間・run列を求める。
  2. 各batchのOUT runについて、最後から2番目のOUTイベント(＝SENSE INT
     コマンドバイトの直前＝対象コマンドの最終コマンドバイト)の直後から、
     次のOUTイベント(SENSE INTコマンドバイト)までの間にある IN $FA
     イベントの値(下位4bit)を報告する。
  3. batch1はRECALIBRATEとSPECIFY/SEEKの順序が不明なため、参考情報として
     全$FA値を出すのみで判定には使わない。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_fdc_ports import parse_iolog
from analyze_boot_fdc_sequence import find_boot_init_window, segment_runs

def analyze(label, path):
    events, masked = parse_iolog(Path(path))
    sub = events["sub"]
    win = find_boot_init_window(sub)
    if win is None:
        print(f"{label}: window not found")
        return
    start, end = win
    window = sub[start:end]
    runs = segment_runs(window)
    out_runs = [r for r in runs if r["kind"] == "OUT"]
    print(f"=== {label} === window index[{start}:{end}) out_runs={len(out_runs)}")
    for bi, r in enumerate(out_runs, start=1):
        # このrun内のOUT $FBイベントをseq順に抽出
        run_events = [e for e in window if e.port == "00FB" and e.kind == "OUT"
                      and r["start_seq"] <= e.seq <= r["end_seq"]]
        if len(run_events) < 2:
            print(f"  batch{bi}: run len={r['len']} (too short, skip)")
            continue
        last_cmd_byte = run_events[-2]  # SENSE INTの直前=対象コマンドの最終バイト
        sense_int_byte = run_events[-1]
        # last_cmd_byte.seq < x < sense_int_byte.seq の範囲にある IN $FA を探す
        fa_in = [e for e in window if e.port == "00FA" and e.kind == "IN"
                 and last_cmd_byte.seq < e.seq < sense_int_byte.seq]
        vals = [ (e.seq, e.value, (e.value & 0x0F) if e.value is not None else None) for e in fa_in ]
        print(f"  batch{bi}: run len={r['len']} last_cmd_seq={last_cmd_byte.seq} "
              f"sense_int_cmd_seq={sense_int_byte.seq} FA(IN) between={vals}")
    print()

if __name__ == "__main__":
    logs = [
        ("d0-boot", "measurements/m6c-sub-d0-boot.iolog.txt.gz"),
        ("d1-files", "measurements/m6c-sub-d1-files.iolog.txt.gz"),
        ("d2-save", "measurements/m6c-sub-d2-save.iolog.txt.gz"),
        ("d5-seqfile", "measurements/m6c-sub-d5-seqfile.iolog.txt.gz"),
    ]
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    for label, path in logs:
        if only and label not in only:
            continue
        analyze(label, path)
