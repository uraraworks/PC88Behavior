#!/usr/bin/env python3
"""合成媒体・署名・偽フロントエンドによる m6f-j 陰性対照。"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_m6fj_disk as check
import m6fj_judge as judge
import m6fj_read as reader
import m6fj_script as script
from make_m6fj_disk import MEDIA, build, offsets
from m6fj_measure import default_core, preflight


def require(ok: bool, name: str) -> None:
    if not ok:
        raise AssertionError(name)


def disk_tests(tmp: pathlib.Path) -> None:
    preflight(HERE / "m6fj_frozen.tsv", tmp / "unused")
    for media in MEDIA:
        require(check.inspect(build(media), media) == [], "G9正例")
    original = build("B1")
    off = offsets(original)

    def broken(name, edit, expected):
        data = bytearray(original)
        edit(data)
        require(check.inspect(data, "B1") == expected, "G9_NG集合_" + name)

    broken("name", lambda b: b.__setitem__(off[(18, 1, 1)], ord("X")), ["entry_name"])
    broken("type", lambda b: b.__setitem__(off[(18, 1, 1)]+9, 0x80), ["file_type"])
    broken("first", lambda b: b.__setitem__(off[(18, 1, 1)]+10, 11), ["entry_first_unit"])
    broken("entry_reserved", lambda b: b.__setitem__(off[(18, 1, 1)]+11, 0), ["entry_reserved"])
    broken("first_unused", lambda b: b.__setitem__(off[(18, 1, 1)]+16, 0), ["first_unused"])
    broken("marker", lambda b: b.__setitem__(off[(18, 1, 13)], 0x10), ["write_marker"])
    broken("fat", lambda b: b.__setitem__(off[(18, 1, 15)]+10, 0xff), ["fat_copies"])
    broken("shape", lambda b: b.__setitem__(28, b[28]^1), ["d88_shape"])
    broken("body", lambda b: b.__setitem__(off[(2, 1, 1)], ord("X")), ["body"])
    for label, unit, value in (("reserved_units", 74, 0xff), ("terminal", 10, 0xc2),
                               ("fat_free", 11, 0xc1)):
        image = bytearray(original)
        for r in (14, 15, 16):
            image[off[(18, 1, r)]+unit] = value
        require(check.inspect(image, "B1") == [label], "G9_NG集合_" + label)
    for media, coordinate, change, expected in (
        ("B2", (18, 1, 14), 0, ["chain"]),
        ("BP", (18, 1, 13), 0, ["write_marker"]),
        ("BF", (18, 1, 14), 0, ["chain"]),
    ):
        image = bytearray(build(media))
        where = offsets(image)[coordinate]
        image[where] = change
        if coordinate == (18, 1, 14):
            for r in (15, 16):
                image[offsets(image)[(18, 1, r)]] = change
        require(check.inspect(image, media) == expected, "G9_NG集合_" + media)
    # 160以降の3複製へ漏えい目印を置いても読み取り・出力に現れない。
    marked = bytearray(original)
    for r in (14, 15, 16):
        marked[off[(18, 1, r)]+160:off[(18, 1, r)]+160+len(b"LEAK_SENTINEL")] = b"LEAK_SENTINEL"
    before = reader.inspect(original, "J-2")
    after = reader.inspect(marked, "J-2")
    require(before == after and after["g8_max_position"] <= 159 and
            "LEAK_SENTINEL" not in json.dumps(after), "G8漏えい目印")
    require(after["body_read_limit"] == len(script.body("J-2")) and
            after["body_read_max_position"] <= after["body_read_limit"], "G7本体上限")
    image_path = tmp / "marked.d88"
    image_path.write_bytes(marked)
    proc = subprocess.run([sys.executable, str(HERE / "m6fj_read.py"), "--image", str(image_path),
                           "--arm", "J-2"], capture_output=True)
    require(proc.returncode == 0 and b"LEAK_SENTINEL" not in proc.stdout + proc.stderr and
            json.loads(proc.stdout)["g8_max_position"] <= 159, "G8出力陰性対照")


def judgments() -> None:
    base = reader.inspect(build("B1"), "J-2")
    signatures = judge.predictions()
    require(len(signatures) == len(set(signatures.values())), "画面候補一意")
    err = next(x for x in signatures if x.startswith("error_"))
    def lines(name):
        return [dict(physical_row=r, char_count=c, sha256=s) for r, c, s in signatures[name]]
    cases = []
    for mode in ("frees", "keeps", "new_slot", "error"):
        new = copy.deepcopy(base)
        if mode == "frees":
            new["fat_0_159"][10] = 0xff
            new["entries"][0]["bytes9_15"][1] = 72
        elif mode == "keeps":
            new["entries"][0]["bytes9_15"][1] = 72
        elif mode == "new_slot":
            new["entries"][0]["name"] = "deleted"
            new["entries"].append({"name": "qsa", "position": 1,
                                    "bytes9_15": [0, 72, 255, 255, 255, 255, 255]})
        cases.append(judge.classify("J-2", base, new, lines(err if mode == "error" else "ok_line")))
    expect = ["overwrite_same_slot_frees_old", "overwrite_same_slot_keeps_old",
              "overwrite_new_slot", err]
    require([x["candidates"] for x in cases] == [[x] for x in expect], "J-II四候補")
    for i, expected in enumerate(expect):
        require(all(expected not in c["candidates"] for j, c in enumerate(cases) if i != j),
                "J-II取り違え")
    b2 = reader.inspect(build("B2"), "J-3")
    for unit, label in ((72, "first_free_in_2_5_order"), (10, "lowest_free_number")):
        new = copy.deepcopy(b2)
        new["fat_0_159"][unit] = 0xc1
        new["entries"].append({"name": "qsc", "position": 1,
                               "bytes9_15": [0, unit, 255, 255, 255, 255, 255]})
        result = judge.classify("J-3", b2, new, lines("ok_line"))
        require(result["candidates"] == [label] and result["allocated_units"] == [unit],
                "J-III取り違え")
    other = copy.deepcopy(b2)
    other["fat_0_159"][11] = 0xc1
    other["entries"].append({"name": "qsc", "position": 1,
                             "bytes9_15": [0, 11, 255, 255, 255, 255, 255]})
    require(judge.classify("J-3", b2, other, lines("ok_line"))["candidates"] == ["other"],
            "J-IIIその他")
    bad_lines = lines("ok_line")
    bad_lines[0]["sha256"] = "0"*64
    require(judge.match_screen(bad_lines) == [], "署名陰性対照")
    require(judge.match_screen(lines("no_line")) == ["no_line"], "J-I陰性候補")
    require(judge.classify("J-1", base, base, lines("ok_line"))["candidates"] == ["ok_line"],
            "J-I_Ok")
    require(judge.classify("J-1", base, base, lines("no_line"))["candidates"] == ["no_line"],
            "J-I_行なし")
    require(judge.classify("J-1", base, base, bad_lines)["candidates"] == ["other"],
            "J-I_その他")
    require(judge.classify("J-4", base, base, lines(err))["candidates"] == [err],
            "J-IV_エラー")
    for arm, number in (("J-4", 61), ("J-5", 68)):
        candidate = f"error_{number}"
        require(judge.classify(arm, base, base, lines(candidate))["candidates"] == [candidate],
                "メッセージ行正例")
        message = judge.errors()[number]
        question_line = [dict(zip(("physical_row", "char_count", "sha256"),
                                  judge.signed(0, "?" + message)))]
        require(judge.classify(arm, base, base, question_line)["candidates"] == ["other"],
                "疑問符つき陰性対照")
    require(judge.classify("J-4", base, base, bad_lines)["candidates"] == ["other"],
            "J-IV_その他")
    saved = copy.deepcopy(base)
    saved["entries"].append({"name": script.NAMES["J-6"], "position": 1,
                             "bytes9_15": [0, 72, 255, 255, 255, 255, 255]})
    wait = judge.classify("J-6", base, saved, lines("no_line"), lines("no_line"))
    error = judge.classify("J-6", base, saved, lines("no_line"), lines(err))
    stuck = judge.classify("J-6", base, base, lines("no_line"), lines("no_line"))
    require([x["candidates"] for x in (wait, error, stuck)] ==
            [["waits_for_media"], [err], ["stuck"]], "J-VI三候補一意")
    require(judge.classify("J-6", base, saved, lines(err), lines("no_line"))[
            "candidates"] == ["other"], "挿入後エラー陰性対照")


FAKE = r'''#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys
sys.path.insert(0,str(pathlib.Path(os.environ['M6FJ_TEST_REPO'])/'tools'))
import m6fj_judge as j
from make_m6fj_disk import offsets
def value(flag): return a[a.index(flag)+1]
def many(flag): return [a[i+1] for i,x in enumerate(a[:-1]) if x==flag]
a=sys.argv[1:]
with open(os.environ['M6FJ_TEST_COUNT'],'a') as f: f.write('1\n')
arm=pathlib.Path(value('--out')).parent.name.split('-r')[0]
disk=pathlib.Path(value('--insert-disk2') if arm=='J-6' else value('--disk2'))
data=bytearray(disk.read_bytes()); off=offsets(data)
name={'J-1':'qsb','J-2':'qsa','J-3':'qsc','J-4':'qsd','J-5':'qse','J-6':'qsf'}[arm]
def fat(unit,n):
 for r in (14,15,16): data[off[(18,1,r)]+unit]=n
def entry(slot,unit):
 p=off[(18,1,1)]+slot*16
 data[p:p+16]=name.encode().ljust(9,b' ')+bytes((0,unit))+b'\xff'*5
def body(unit,n):
 payload=f'10 PRINT {n}\r\n'.encode()+b'\x1a'
 p=off[(unit//4,(unit//2)%2,(unit*8)%16+1)]
 data[p:p+len(payload)]=payload
choice='ok_line'
if arm=='J-1': entry(0,72); fat(72,0xc1); body(72,1)
elif arm=='J-2': entry(0,72); fat(10,0xff); fat(72,0xc1); body(72,2)
elif arm=='J-3': entry(1,72); fat(72,0xc1)
elif arm=='J-4': choice='error_61'
elif arm=='J-5': choice='error_68'
elif arm=='J-6': choice='no_line'; entry(0,72); fat(72,0xc1)
disk.write_bytes(data)
def signed(row,s): return row,len(s),hashlib.sha256(f'{row}\t{s}\n'.encode()).hexdigest()
fkey=signed(19,'FKEY')
prompt=signed(1,'LEAK_SENTINEL')
pred=j.predictions()
def screen(name): return list(pred[name])+[prompt,fkey]
def write(name,rows):
 rows=sorted(rows)
 out.write(f'snapshot_id\t{name}\nphysical_row\tchar_count\tsha256\n')
 for row,count,digest in rows: out.write(f'{row}\t{count}\t{digest}\n')
 whole=hashlib.sha256(''.join(f'{r}\t{c}\t{s}\n' for r,c,s in rows).encode()).hexdigest()
 out.write(f'line_count\t{len(rows)}\nchar_count\t{sum(x[1] for x in rows)}\nsha256\t{whole}\n')
with pathlib.Path(value('--out')).open('w') as out:
 for name in [x.split(':')[0] for x in many('--screen-signature-at')]:
  rows=[signed(0,'BASELINE'),fkey] if name=='baseline' else screen('no_line' if name=='preinsert' else choice)
  write(name,rows)
pathlib.Path(value('--io-log')).write_text('synthetic\n')
'''


def driver_tests(tmp: pathlib.Path) -> None:
    fixture = tmp / "core-fixture"
    (fixture / "tools").mkdir(parents=True)
    (fixture / "tools" / "lib_l3_measure.sh").write_bytes((HERE / "lib_l3_measure.sh").read_bytes())
    vendor = fixture.parent / "vendor" / "quasi88-libretro"
    vendor.mkdir(parents=True)
    expected = vendor / "quasi88_libretro.synthetic"
    expected.touch()
    require(default_core(fixture) == str(expected), "コア既定の共通規則")
    fake = tmp / "fake.py"
    fake.write_text(FAKE, encoding="ascii")
    fake.chmod(0o755)
    (tmp / "rom").mkdir()
    (tmp / "ref").mkdir()
    (tmp / "ref" / "N88_FE.D88").write_bytes(b"SYNTHETIC")
    count = tmp / "count"
    base = {**os.environ, "M6FJ_TEST_MODE": "1", "M6FJ_FRONTEND": str(fake),
            "M6FJ_TEST_ROM_DIR": str(tmp / "rom"), "M6FJ_TEST_DISK_DIR": str(tmp / "ref"),
            "M6FJ_TEST_CORE": "synthetic", "M6FJ_TEST_REPO": str(HERE.parent),
            "M6FJ_TEST_COUNT": str(count)}

    def run(label, extra=None, options=()):
        count.write_text("", encoding="ascii")
        proc = subprocess.run(["bash", str(HERE / "measure_m6fj.sh"), "--work", str(tmp / label), *options],
                              env={**base, **(extra or {})}, capture_output=True, text=True)
        return proc, len(count.read_text().splitlines())

    good, n = run("good")
    require(good.returncode == 0 and n == 12, "偽フロントエンド正例")
    result = (tmp / "good" / "result.json").read_text()
    require("LEAK_SENTINEL" not in result + good.stdout + good.stderr,
            "画面本文漏えい")
    judgments = json.loads(result)["judgment"]["judgments"]
    require(judgments == {"J-1": "ok_line", "J-2": "overwrite_same_slot_frees_old",
                          "J-3": "first_free_in_2_5_order", "J-4": "error_61",
                          "J-5": "error_68", "J-6": "waits_for_media"}, "全腕判定")
    subset, n = run("subset", options=("--arms", "J-4,J-5,J-6"))
    require(subset.returncode == 0 and n == 6, "追補腕だけ2走")
    selected = json.loads((tmp / "subset" / "result.json").read_text())
    require(set(selected["observations"]) == {"J-4", "J-5", "J-6"} and
            selected["judgment"]["judgments"] == {"J-4": "error_61", "J-5": "error_68",
                                                   "J-6": "waits_for_media"}, "追補腕だけ判定")
    invalid, n = run("invalid", options=("--arms", "J-4,J-4"))
    require(invalid.returncode != 0 and n == 0 and json.loads(invalid.stdout)["reason"] == "arms_invalid",
            "重複腕の陰性対照")
    values = (HERE / "m6fj_frozen.tsv").read_text()
    bad = tmp / "bad.tsv"
    bad.write_text(values.replace("manifest_sha256\t", "manifest_sha256\t0", 1))
    proc, n = run("bad", {"M6FJ_TEST_FROZEN": str(bad)})
    require(proc.returncode != 0 and n == 0 and json.loads(proc.stdout)["reason"] == "G3", "凍結破壊起動0")
    proc, n = run("uppercase", {"M6FJ_TEST_UPPERCASE": "1"})
    require(proc.returncode != 0 and n == 0 and json.loads(proc.stdout)["reason"] == "G3", "大小不一致G3起動0")


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="m6fj-selftest-") as value:
            tmp = pathlib.Path(value)
            disk_tests(tmp)
            judgments()
            if "--preflight" not in sys.argv:
                driver_tests(tmp)
        print("OK m6f-j: G8・G9・全候補・起動前関門・偽フロントエンド")
        return 0
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
        print("NG m6f-j: " + type(exc).__name__ + ":" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
