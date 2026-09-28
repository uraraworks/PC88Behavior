#!/usr/bin/env python3
"""追補2の媒体、候補、関門を合成入力だけで検査する。"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_m6fi_add2 as gate
import check_m6fi_add2_disk as check
import derive_m6fi_add2 as derive
import judge_m6fi_add2 as judge
import make_m6fi_add2_disk as disk
import predict_m6fi_add2 as predict


def require(value: bool, label: str) -> None:
    if not value:
        raise AssertionError(label)


def disk_tests(tmp: Path) -> None:
    doc = disk.manifest()
    image = disk.build_disk(doc)
    require(check.inspect_image(image, doc) == [], "G15正例")
    manifest = tmp / "manifest.json"
    manifest.write_bytes(disk.canonical(doc))
    gate.verify(manifest, HERE / "m6fi_add2_candidates_frozen.tsv",
                HERE / "m6fi_add2_frozen.tsv", HERE / "predict_m6fi_add2.py")
    offsets = disk.sector_offsets(image)
    directory = offsets[(18, 1, 1)]
    # 各故障でNG集合を完全一致させる。qieの先頭は単位3の第1セクタ。
    qie_body = offsets[(0, 1, 9)]
    cases = (
        ("entry_name", directory + 3 * 16, ord("X")),
        ("file_type", directory + 3 * 16 + 9, 0x80),
        ("entry_reserved", directory + 3 * 16 + 11, 0),
        ("first_unused", directory + 4 * 16, 0),
        ("body", qie_body, ord("X")),
    )
    for name, pos, value in cases:
        bad = bytearray(image)
        bad[pos] = value
        require(check.inspect_image(bad, doc) == [name], "G15陰性対照_" + name)
    changed = copy.deepcopy(doc)
    changed["entries"][-1]["name"] = "QIE"
    require(check.inspect_image(disk.build_disk(changed), changed) == ["entry_name"],
            "qie名前NG集合")
    bad_frozen = tmp / "bad-frozen.tsv"
    bad_frozen.write_text((HERE / "m6fi_add2_frozen.tsv").read_text().replace(
        "45001b96fb6b8f5fa43594fd9cbb11403168a907fd6243dc9236940d7fe9f3c6",
        "0" * 64), encoding="ascii")
    try:
        gate.verify(manifest, HERE / "m6fi_add2_candidates_frozen.tsv", bad_frozen,
                    HERE / "predict_m6fi_add2.py")
    except ValueError:
        pass
    else:
        raise AssertionError("凍結破壊")


def observation(arm: str, candidate: str) -> dict:
    lines = predict.predict(arm, candidate)
    summary = {"line_count": len(lines), "char_count": sum(x.char_count for x in lines),
               "sha256": predict.whole(lines)}
    return {"screen": summary, "late_screen": summary,
            "load_screen": summary if arm == "E-3" else None,
            "load_late_screen": summary if arm == "E-3" else None,
            "entry_lines": [{"physical_row": x.physical_row, "char_count": x.char_count,
                             "sha256": x.sha256} for x in lines],
            "input_wait": True, "load_input_wait": arm == "E-3",
            "reference_unchanged": True, "output_audit_clean": True,
            "fkey_unchanged": True, "extra_lines_absent": True,
            "g13": {"line_sha": True, "char_count": True, "physical_row": True}}


def prediction_tests(tmp: Path) -> None:
    require((HERE / "m6fi_add2_candidates_frozen.tsv").read_bytes() ==
            predict.render_candidates(), "候補凍結")
    candidates = derive.load_candidates(HERE / "m6fi_add2_candidates_frozen.tsv")
    for arm in predict.ARMS:
        signatures = [predict.predict(arm, key) for key in predict.candidate_ids(arm)]
        require(len(signatures) == len(set(signatures)), "候補一意_" + arm)
    selected = {"I-4'": "ok_line", "E-2'": "direct_msg_57",
                "E-3": "upto_error", "E-3m": "direct_msg_2"}
    arms = {arm: [observation(arm, key) for _ in (1, 2)] for arm, key in selected.items()}

    def run(values):
        path = tmp / "observations.json"
        path.write_text(json.dumps({"format": "m6fi-add2-observations-v1", "arms": values},
                                   sort_keys=True, separators=(",", ":")), encoding="ascii")
        loaded, _ = derive.load_observations(path)
        return derive.derive(loaded, candidates)

    result = run(arms)
    require(result["judgments"] == selected and result["overall"] == "classified", "導出正例")
    result["input_sha256"] = "0" * 64
    require(judge.recompute(result)["judgments"] == list(selected.values()), "判定正例")
    for arm, alternative in (("I-4'", "no_line"), ("E-2'", "direct_msg_53"),
                             ("E-3", "all_numbered"), ("E-3", "none_loaded"),
                             ("E-3m", "ok_line"), ("E-3m", "direct_msg_57")):
        bad = copy.deepcopy(arms)
        bad[arm] = [observation(arm, alternative) for _ in (1, 2)]
        value = run(bad)
        require(value["matches"][arm] == [alternative] and
                value["judgments"][arm] == alternative, "候補取り違え_" + arm)
    for arm in predict.ARMS:
        bad = copy.deepcopy(arms)
        if bad[arm][0]["entry_lines"]:
            bad[arm][0]["entry_lines"][0]["sha256"] = "0" * 64
            require(run(bad)["matches"][arm] == [], "行署名陰性対照_" + arm)
    bad = copy.deepcopy(arms)
    bad["I-4'"][0]["LEAK_SENTINEL"] = "LEAK_SENTINEL"
    path = tmp / "leak.json"
    path.write_text(json.dumps({"format": "m6fi-add2-observations-v1", "arms": bad}),
                    encoding="ascii")
    proc = subprocess.run([sys.executable, str(HERE / "derive_m6fi_add2.py"),
                           "--observations", str(path)], capture_output=True)
    require(proc.returncode != 0 and b"LEAK_SENTINEL" not in proc.stdout + proc.stderr,
            "漏えい陰性対照")


FAKE = '''#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys
sys.path.insert(0,str(pathlib.Path(os.environ['M6FI_ADD2_SELFTEST_REPO'])/'tools'))
import predict_m6fi_add2 as p
def one(a,n): return a[a.index(n)+1]
def many(a,n): return [a[i+1] for i,v in enumerate(a[:-1]) if v==n]
def h(row,body): return row,len(body),hashlib.sha256(f'{row}\\t{body}\\n'.encode()).hexdigest()
def write(out,snaps):
 with out.open('w',encoding='ascii') as f:
  for name,rows in snaps:
   rows=sorted(rows)
   f.write(f'snapshot_id\\t{name}\\nphysical_row\\tchar_count\\tsha256\\n')
   for row,count,digest in rows: f.write(f'{row}\\t{count}\\t{digest}\\n')
   whole=hashlib.sha256(''.join(f'{r}\\t{c}\\t{s}\\n' for r,c,s in rows).encode()).hexdigest()
   f.write(f'line_count\\t{len(rows)}\\nchar_count\\t{sum(x[1] for x in rows)}\\nsha256\\t{whole}\\n')
a=sys.argv[1:]; out=pathlib.Path(one(a,'--out')); io=pathlib.Path(one(a,'--io-log'))
arm=out.parent.name.rsplit('-r',1)[0]
with open(os.environ['M6FI_ADD2_SELFTEST_COUNTER'],'a') as f: f.write('1\\n')
choice={"I-4'":'ok_line',"E-2'":'direct_msg_57','E-3':'upto_error','E-3m':'direct_msg_2'}[arm]
signed=[(x.physical_row,x.char_count,x.sha256) for x in p.predict(arm,choice)]
prompt=h(max((x[0] for x in signed),default=-1)+1,'LEAK_SENTINEL')
fkey=h(19,'FKEY')
baseline=[h(0,'LEAK_SENTINEL'),fkey]
final=signed+[prompt,fkey]
load=[h(0,'LEAK_SENTINEL'),fkey]
wanted={x.split(':',1)[0] for x in many(a,'--screen-signature-at')}
typed=many(a,'--type-at')
if arm=='E-3':
 assert 'load' in wanted and 'load_late' in wanted and '4000' in typed
else: assert 'load' not in wanted and '4000' not in typed
write(out,[item for item in [('baseline',baseline),('load',load),('load_late',list(load)),('final',final),('late',list(final))] if item[0] in wanted])
io.write_text('# synthetic iolog\\n',encoding='ascii')
'''


def driver_tests(tmp: Path) -> None:
    fake = tmp / "fake_frontend.py"
    fake.write_text(FAKE, encoding="ascii")
    fake.chmod(0o755)
    (tmp / "rom").mkdir()
    (tmp / "refdisk").mkdir()
    (tmp / "refdisk" / "N88_FE.D88").write_bytes(b"SYNTHETIC-REFERENCE-DISK")
    counter = tmp / "count.txt"
    base = {**os.environ, "M6FI_ADD2_FRONTEND": str(fake), "M6FI_ADD2_TEST_MODE": "1",
            "M6FI_ADD2_TEST_FAST_GATES": "1", "M6FI_ADD2_TEST_CORE": "selftest-core",
            "M6FI_ADD2_TEST_ROM_DIR": str(tmp / "rom"),
            "M6FI_ADD2_TEST_DISK_DIR": str(tmp / "refdisk"),
            "M6FI_ADD2_SELFTEST_REPO": str(HERE.parent),
            "M6FI_ADD2_SELFTEST_COUNTER": str(counter)}

    def run(name, extra=None):
        counter.write_text("", encoding="ascii")
        env = {**base, **(extra or {}), "PC88_M6FI_ADD2_WORK": str(tmp / name)}
        proc = subprocess.run(["bash", str(HERE / "measure_m6fi_add2.sh")], env=env,
                              capture_output=True, text=True)
        return proc, len(counter.read_text().splitlines())

    positive, count = run("positive")
    require(positive.returncode == 0 and count == 8, "ドライバ正例")
    output = tmp / "positive"
    require(sorted(p.name for p in output.iterdir()) ==
            ["derived.json", "judgment.json", "observations.json", "summary.json"],
            "出力許可リスト")
    require(json.loads((output / "judgment.json").read_text())["judgments"] ==
            ["ok_line", "direct_msg_57", "upto_error", "direct_msg_2"], "ドライバ判定")
    require(all(b"LEAK_SENTINEL" not in p.read_bytes() for p in output.iterdir()) and
            "LEAK_SENTINEL" not in positive.stdout + positive.stderr, "漏えい目印")
    for gate_id in (f"G{i}" for i in range(9)):
        proc, count = run("fail-" + gate_id,
                          {"M6FI_ADD2_TEST_FAIL_GATE": gate_id})
        require(proc.returncode != 0 and count == 0 and
                json.loads(proc.stdout)["failed_gates"] == [gate_id],
                "起動前NG集合_" + gate_id)
    bad = tmp / "bad-frozen-driver.tsv"
    bad.write_text((HERE / "m6fi_add2_frozen.tsv").read_text().replace(
        "45001b96fb6b8f5fa43594fd9cbb11403168a907fd6243dc9236940d7fe9f3c6",
        "0" * 64), encoding="ascii")
    proc, count = run("bad-frozen", {"M6FI_ADD2_TEST_FROZEN": str(bad)})
    require(proc.returncode != 0 and count == 0 and
            json.loads(proc.stdout)["failed_gates"] == ["G4"], "凍結破壊起動0")


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="m6fi-add2-selftest-") as value:
            tmp = Path(value)
            if "--prediction-only" not in sys.argv:
                disk_tests(tmp)
            if "--disk-only" not in sys.argv:
                prediction_tests(tmp)
            if len(sys.argv) == 1:
                driver_tests(tmp)
        print("OK m6f-i 追補2: G15・候補・関門・漏えい・偽フロントエンド")
        return 0
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
        print("NG m6f-i 追補2: " + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
