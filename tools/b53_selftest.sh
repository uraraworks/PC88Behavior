#!/usr/bin/env bash
# 自作main・媒体・subだけを実行し、公開済みB52dの集計値と照合する。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >/dev/null
# 2バイト目を立ち上がり時に読む故障を一時生成物だけへ入れる。
PYTHONPATH="$REPO/src/l3_service" python3 - "$work/fault" <<'PY'
import pathlib, sys
import make_subrom as m
source = pathlib.Path(m.__file__).read_text()
# 固定入口の配置は生成器に任せ、受信ルーチン内の手順だけを改変する。
old = ('    a.label("RECV_FIRST_ARMED")\n'
       '    a.call("WAIT_FE_RECV_DATA_READY")       # 手順2: 相手のデータ準備待ち(bit0=1)\n'
       '    a.out_imm(0xFF, PH_RECV_START_CLR)      # 手順3: OUT $FF,0x0A\n'
       '    a.in_port(P_PIO_A)                      # 手順4: IN $FC（main OUT $FDと対応）')
assert source.count(old) == 1
source = source.replace(old, old + '\n    a.in_port(P_PIO_A)  # 故障: ACK前、bit0立ち上がり側で2バイト目を読む\n    a.ld_c_a()')
old = '    a.label("_general_load_pair_second")\n    a.in_port(P_PIO_A)'
assert source.count(old) == 1
source = source.replace(old, '    a.label("_general_load_pair_second")\n    a.ld_a_c()')
ns = dict(m.__dict__)
exec(compile(source, m.__file__, 'exec'), ns)
rom, used = ns['build']()
assert used <= m.SUB_ROM_FETCH_WINDOW
out = pathlib.Path(sys.argv[1]); out.mkdir()
(out/'DISK.ROM').write_bytes(rom)
PY
for variant in sub fault; do
  "$REPO/tools/measure_b52d.sh" --work "$work/run-$variant" \
    --dry-run-sub-rom "$work/$variant/DISK.ROM" --output-dir "$work/results-$variant"
done
python3 - "$REPO/measurements/b52d-official-1.tsv" "$work" <<'PY'
import csv, pathlib, sys
def read(path):
    with open(path) as f:
        return {int(r['row']): r for r in csv.DictReader(f, delimiter='\t')}
expected = read(sys.argv[1]); root = pathlib.Path(sys.argv[2])
fields = ('layout', 'before', 'after', 'executed')
def agrees(rows):
    return all(rows[n]['complete'] == '1' and rows[n]['timeout'] == '0'
               and rows[n]['count'] == '64'
               and all(rows[n][k] == expected[n][k] for k in fields)
               for n in (1, 2, 3, 4, 6, 7))
for run in (1, 2):
    assert agrees(read(root / f'results-sub/b52d-self-{run}.tsv')), '通常版が不一致'
    fault = read(root / f'results-fault/b52d-self-{run}.tsv')
    assert not agrees(fault), '立ち上がり読出しの故障を見逃した'
    assert fault[2]['complete'] == '1' and fault[2]['layout'] != expected[2]['layout'], '故障原因が違う'
print('B53 自己検査 OK（行1〜4、6、7一致・立ち上がり読出し故障を検出）')
PY
