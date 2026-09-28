#!/usr/bin/env python3
"""m6f-i 器具を自作D88・合成署名・偽フロントエンドで検査する。"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_m6fi_disk as check
import derive_m6fi as derive
import judge_m6fi as judge
import make_m6fi_disk as disk
import predict_m6fi as predict


def require(ok: bool, label: str) -> None:
    if not ok:
        raise AssertionError(label)


def offsets(image: bytes) -> dict[tuple[int, int, int], int]:
    starts = sorted(v for v in (struct.unpack_from("<I", image, 32 + 4 * i)[0]
                                for i in range(164)) if v)
    result = {}
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(image)
        pos = start
        while pos < end:
            result[tuple(image[pos:pos + 3])] = pos + 16
            pos += 16 + struct.unpack_from("<H", image, pos + 14)[0]
    return result


def disk_tests(tmp: pathlib.Path) -> None:
    doc = disk.manifest()
    image = disk.build_disk(doc)
    require(check.inspect_image(image, doc) == [], "G15正例")
    require(disk.canonical(doc) == disk.canonical(disk.manifest()), "媒体決定論")
    require("make_m6fi_disk" not in (HERE / "check_m6fi_disk.py").read_text(), "検査独立")
    off = offsets(image)
    directory = off[(18, 1, 1)]
    body = off[(0, 0, 1)]
    eof = body + len(bytes.fromhex(doc["entries"][0]["body_hex"])) - 1

    def one(label, mutate):
        bad = bytearray(image)
        mutate(bad)
        require(check.inspect_image(bad, doc) == [label], "G15_" + label)

    def fat(bad, unit, value, copies=(14, 15, 16)):
        for r in copies:
            bad[off[(18, 1, r)] + unit] = value

    one("d88_shape", lambda b: b.__setitem__(28, b[28] ^ 1))
    one("entry_name", lambda b: b.__setitem__(directory, ord("X")))
    one("file_type", lambda b: b.__setitem__(directory + 9, 0x80))
    one("entry_reserved", lambda b: b.__setitem__(directory + 11, 0))
    one("first_unused", lambda b: b.__setitem__(directory + 48, 0))
    one("fat_copies", lambda b: fat(b, 0, 0xFF, (15,)))
    one("reserved_units", lambda b: fat(b, 74, 0xFF))
    one("write_marker", lambda b: b.__setitem__(off[(18, 1, 13)], 0x10))
    one("chain", lambda b: fat(b, 0, 0xFF))
    one("terminal", lambda b: fat(b, 0, 0xC2))
    one("unit_unique", lambda b: b.__setitem__(directory + 16 + 10, 0))
    one("fat_free", lambda b: fat(b, 3, 0xC1))
    one("body", lambda b: b.__setitem__(body, ord("X")))
    one("eof_1a", lambda b: b.__setitem__(eof, 0))
    manifest_path = tmp / "manifest.json"
    image_path = tmp / "ascii.d88"
    manifest_path.write_bytes(disk.canonical(doc))
    image_path.write_bytes(image)
    cmd = [sys.executable, str(HERE / "check_m6fi_disk.py"), str(manifest_path),
           "--image", str(image_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    require(result.returncode == 0 and json.loads(result.stdout) == {"failures": []}, "G15_CLI正例")
    require(hashlib.sha256(manifest_path.read_bytes()).hexdigest() == dict(
        row.split("\t") for row in (HERE / "m6fi_frozen.tsv").read_text().splitlines()
        )["manifest_sha256"], "媒体凍結")


def observation(arm: str, candidate: str) -> dict:
    lines = predict.predict(arm, candidate)
    digest = predict.whole(lines)
    summary = {"line_count": len(lines), "char_count": sum(x.char_count for x in lines),
               "sha256": digest}
    return {"screen": summary, "late_screen": summary,
            "load_screen": summary if arm in predict.ARMS[:3] else None,
            "load_late_screen": summary if arm in predict.ARMS[:3] else None,
            "entry_lines": [{"physical_row": x.physical_row, "char_count": x.char_count,
                             "sha256": x.sha256} for x in lines],
            "input_wait": True, "load_input_wait": arm in predict.ARMS[:3],
            "reference_unchanged": True, "output_audit_clean": True,
            "fkey_unchanged": True, "extra_lines_absent": True,
            "g13": {"line_sha": True, "char_count": True, "physical_row": True}}


def prediction_tests(tmp: pathlib.Path) -> None:
    require((HERE / "m6fi_candidates_frozen.tsv").read_bytes() ==
            predict.render_candidates(), "候補凍結")
    candidates = derive.load_candidates(HERE / "m6fi_candidates_frozen.tsv")
    for arm in predict.ARMS:
        signatures = [tuple((x.physical_row, x.char_count, x.sha256)
                            for x in predict.predict(arm, candidate))
                      for candidate in predict.candidate_ids(arm)]
        require(len(signatures) == len(set(signatures)), "候補一意_" + arm)
    selected = {"I-1": "loads_lines", "I-2": "replaces", "I-3": "sorted",
                "I-4": "ok_only", "E-1": "err_53", "E-2": "err_2"}
    arms = {arm: [observation(arm, candidate) for _ in (1, 2)]
            for arm, candidate in selected.items()}
    derived = derive.derive(derive.load_observations(_write_observations(tmp, arms))[0], candidates)
    derived["input_sha256"] = "0" * 64
    require(derived["overall"] == "classified" and derived["judgments"] == selected,
            "導出正例")
    require(judge.recompute(derived)["judgments"] == list(selected.values()), "判定正例")
    for arm, alternative in (("I-2", "merges"), ("I-3", "file_order"),
                             ("E-1", "err_54"), ("E-2", "loads_without_error")):
        changed = copy.deepcopy(arms)
        changed[arm] = [observation(arm, alternative) for _ in (1, 2)]
        result = derive.derive(derive.load_observations(_write_observations(tmp, changed))[0],
                               candidates)
        require(result["judgments"][arm] == alternative, "取り違え_" + arm)
    for n in range(256):
        require(predict.predict("E-1", f"err_{n}") != predict.predict(
            "E-1", f"err_{(n + 1) % 256}"), "ERR一意")
    for arm in predict.ARMS:
        lines = list(arms[arm][0]["entry_lines"])
        if not lines:
            continue
        for field, value in (("sha256", "f" * 64), ("char_count", lines[0]["char_count"] + 1),
                             ("physical_row", lines[-1]["physical_row"] + 1)):
            changed = copy.deepcopy(arms)
            changed[arm][0]["entry_lines"][-1 if field == "physical_row" else 0][field] = value
            result = derive.derive(derive.load_observations(
                _write_observations(tmp, changed))[0], candidates)
            require(result["matches"][arm] == [], "署名破壊_" + arm + field)
    leak = copy.deepcopy(arms)
    leak["I-1"][0]["LEAK_SENTINEL"] = "LEAK_SENTINEL"
    obs_path = _write_observations(tmp, leak)
    cmd = [sys.executable, str(HERE / "derive_m6fi.py"), "--observations", str(obs_path)]
    result = subprocess.run(cmd, capture_output=True)
    require(result.returncode != 0 and b"LEAK_SENTINEL" not in result.stdout + result.stderr,
            "漏えい例外")


def _write_observations(tmp: pathlib.Path, arms: dict) -> pathlib.Path:
    path = tmp / "observations-input.json"
    path.write_text(json.dumps({"format": "m6fi-observations-v1", "arms": arms},
                               sort_keys=True, separators=(",", ":")), encoding="ascii")
    return path


FAKE = '''#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys
sys.path.insert(0,str(pathlib.Path(os.environ['M6FI_SELFTEST_REPO'])/'tools'))
import predict_m6fi as p
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
with open(os.environ['M6FI_SELFTEST_COUNTER'],'a') as f: f.write('1\\n')
choice={'I-1':'loads_lines','I-2':'replaces','I-3':'sorted','I-4':'ok_only','E-1':'err_53','E-2':'err_2'}[arm]
signed=[(x.physical_row,x.char_count,x.sha256) for x in p.predict(arm,choice)]
prompt=h(max((x[0] for x in signed),default=-1)+1,'LEAK_SENTINEL')
fkey=h(19,'FKEY')
baseline=[h(0,'LEAK_SENTINEL'),fkey]
if os.environ.get('M6FI_SELFTEST_BAD_BASELINE'): baseline.append(h(5,'X'))
final=signed+[prompt,fkey]
load=[h(0,'LEAK_SENTINEL'),fkey]
load_late=list(load)
if os.environ.get('M6FI_SELFTEST_BAD_LOAD'): load_late=[h(0,'CHANGED'),fkey]
wanted={x.split(':',1)[0] for x in many(a,'--screen-signature-at')}
if arm in ('I-1','I-2','I-3'):
 assert 'load' in wanted and 'load_late' in wanted
 assert '4000' in many(a,'--type-at')
else: assert 'load' not in wanted
write(out,[item for item in [('baseline',baseline),('load',load),('load_late',load_late),('final',final),('late',list(final))] if item[0] in wanted])
io.write_text('# synthetic iolog\\n',encoding='ascii')
'''


def driver_tests(tmp: pathlib.Path) -> None:
    fake = tmp / "fake_frontend.py"
    fake.write_text(FAKE, encoding="ascii")
    fake.chmod(0o755)
    (tmp / "rom").mkdir()
    (tmp / "refdisk").mkdir()
    (tmp / "refdisk" / "N88_FE.D88").write_bytes(b"SYNTHETIC-REFERENCE-DISK")
    counter = tmp / "count.txt"
    base = {**os.environ, "M6FI_FRONTEND": str(fake), "M6FI_TEST_MODE": "1",
            "M6FI_TEST_FAST_GATES": "1", "M6FI_TEST_CORE": "selftest-core",
            "M6FI_TEST_ROM_DIR": str(tmp / "rom"),
            "M6FI_TEST_DISK_DIR": str(tmp / "refdisk"),
            "M6FI_SELFTEST_REPO": str(HERE.parent),
            "M6FI_SELFTEST_COUNTER": str(counter)}

    def run(name, extra=None):
        counter.write_text("", encoding="ascii")
        env = {**base, **(extra or {}), "PC88_M6FI_WORK": str(tmp / name)}
        proc = subprocess.run(["bash", str(HERE / "measure_m6fi.sh")], env=env,
                              capture_output=True, text=True)
        return proc, len(counter.read_text().splitlines())

    positive, count = run("positive")
    require(positive.returncode == 0 and count == 12, "ドライバ正例")
    result = tmp / "positive"
    require(sorted(path.name for path in result.iterdir()) ==
            ["derived.json", "judgment.json", "observations.json", "summary.json"],
            "出力許可リスト")
    require(json.loads((result / "judgment.json").read_text())["judgments"] ==
            ["loads_lines", "replaces", "sorted", "ok_only", "err_53", "err_2"],
            "ドライバ判定")
    require(all(b"LEAK_SENTINEL" not in path.read_bytes() for path in result.iterdir()) and
            "LEAK_SENTINEL" not in positive.stdout + positive.stderr, "本文漏えい")
    for gate in (f"G{i}" for i in range(9)):
        proc, count = run("fail-" + gate, {"M6FI_TEST_FAIL_GATE": gate})
        value = json.loads(proc.stdout)
        require(proc.returncode != 0 and count == 0 and
                value["failed_gates"] == [gate] and value["frontend_launch_count"] == 0,
                "起動前関門_" + gate)
    bad = tmp / "bad-frozen.tsv"
    values = dict(row.split("\t") for row in (HERE / "m6fi_frozen.tsv").read_text().splitlines())
    values["candidates_sha256"] = "0" * 64
    bad.write_text("".join(key + "\t" + value + "\n" for key, value in values.items()), encoding="ascii")
    proc, count = run("bad-frozen", {"M6FI_TEST_FROZEN": str(bad)})
    require(proc.returncode != 0 and count == 0 and
            json.loads(proc.stdout)["failed_gates"] == ["G4"], "凍結破壊起動0")
    proc, count = run("bad-baseline", {"M6FI_SELFTEST_BAD_BASELINE": "1"})
    require(proc.returncode == 0 and count == 1 and
            "inconclusive_cls_baseline" in proc.stdout, "G14陰性対照")
    proc, count = run("bad-load", {"M6FI_SELFTEST_BAD_LOAD": "1"})
    require(proc.returncode != 0 and count == 2 and
            json.loads(proc.stdout)["failed_gates"] == ["run_gate"], "LOAD完了陰性対照")


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="m6fi-selftest-") as value:
            tmp = pathlib.Path(value)
            if "--prediction-only" not in sys.argv:
                disk_tests(tmp)
            if "--disk-only" not in sys.argv:
                prediction_tests(tmp)
            if len(sys.argv) == 1:
                driver_tests(tmp)
        print("OK m6f-i: G15・候補・ERR・関門・漏えい・偽フロントエンド")
        return 0
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
        print("NG m6f-i: " + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
