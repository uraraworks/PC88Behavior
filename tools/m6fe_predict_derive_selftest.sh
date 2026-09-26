#!/usr/bin/env bash
# m6f-e 器具C（54候補予測・導出・判定）の合成自己検査。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/m6fe-c.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

python3 "$REPO/tools/make_m6fe_disk.py" "$WORK/media" >"$WORK/generator.out" 2>"$WORK/generator.err"
python3 "$REPO/tools/check_m6fe_candidates.py" "$WORK/media/manifest.json" \
  >"$WORK/g4.out" 2>"$WORK/g4.err"

REPO="$REPO" WORK="$WORK" python3 - <<'PY'
from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import subprocess
import sys

repo = pathlib.Path(os.environ["REPO"])
work = pathlib.Path(os.environ["WORK"])
sys.path.insert(0, str(repo / "tools"))
import derive_m6fe as derive
import predict_m6fe as predict

manifest_path = work / "media" / "manifest.json"
manifest = predict._manifest(manifest_path)
candidates_path = repo / "tools" / "m6fe_candidates_frozen.tsv"
candidates = derive.load_candidates(candidates_path)
canary = "ZQLEAK9"

predict_source = (repo / "tools" / "predict_m6fe.py").read_text(encoding="utf-8")
if "import make_m6fe_disk" in predict_source or "from make_m6fe_disk import" in predict_source:
    raise SystemExit("NG predictor_independence")


def fail(label):
    print("NG " + label)
    raise SystemExit(1)


def ok(label):
    print("OK " + label)


def triples(lines):
    return tuple((v.physical_row, v.char_count, v.sha256) for v in lines)


def bodies_for(doc, arm, candidate):
    layout, name_rule, type_rule, size_rule = predict._candidate_parts(candidate)
    media = predict._arm_media(doc, arm)
    items = [predict._entry_text(entry, name_rule, type_rule, size_rule)
             for entry in media["entries"]]
    lines = predict._layout_lines(items, layout)
    visible = (lines + [""])[-predict.SCROLL_ROWS:]
    return visible[:-predict.WAIT_ROWS]


def signed_bodies(bodies, row_offset=0):
    return triples([predict._hash_line(index + row_offset, body)
                    for index, body in enumerate(bodies)])


# 54候補それぞれについて、全7腕の積集合が当該候補1つだけになる。
for intended in predict.candidate_ids():
    remaining = set(predict.candidate_ids())
    for arm in predict.LAYOUT_ARMS:
        actual = candidates[(intended, arm)]
        remaining &= {candidate for candidate in predict.candidate_ids()
                      if candidates[(candidate, arm)] == actual}
    if remaining != {intended}:
        fail("candidate_uniqueness")
ok("54候補すべての合成画面が意図した1候補だけを残す")


# §6.3の故障を個別に作り、NG項目集合を名前まで完全一致で検査する。
base_id = "files_layout_rule_G5_SPLIT63_80DOT_00BLANK_SECTORS"
base_l11 = candidates[(base_id, "L11")]
fault_pairs = {}

changed = copy.deepcopy(manifest)
changed["media"]["L11"]["entries"][0]["name"] = "X"
fault_pairs["one_character_replacement"] = (
    base_l11, triples(predict.predict_candidate(changed, "L11", base_id)))

base_bodies = bodies_for(manifest, "L11", base_id)
space_base = list(base_bodies); space_base[0] += "  "
more = list(base_bodies); more[0] += "   "
less = list(base_bodies); less[0] += " "
fault_pairs["trailing_space_more"] = (signed_bodies(space_base), signed_bodies(more))
fault_pairs["trailing_space_less"] = (signed_bodies(space_base), signed_bodies(less))

swapped = list(base_bodies)
swapped[0], swapped[1] = swapped[1], swapped[0]
fault_pairs["line_swap"] = (base_l11, signed_bodies(swapped))

shifted = list(base_l11)
row, count, digest = shifted[0]
shifted[0] = (row + 1, count, digest)
fault_pairs["physical_row_shift"] = (base_l11, tuple(shifted))

g4_id = base_id.replace("_G5_", "_G4_")
fault_pairs["four_five_per_row_swap"] = (base_l11, candidates[(g4_id, "L11")])
type_id = base_id.replace("80DOT_00BLANK", "80BLANK_00DOT")
fault_pairs["type_mark_swap"] = (base_l11, candidates[(type_id, "L11")])

deleted = copy.deepcopy(manifest)
extra = copy.deepcopy(deleted["media"]["L11"]["entries"][0])
extra["name"] = "DELONE"
deleted["media"]["L11"]["entries"].insert(2, extra)
fault_pairs["deleted_entry_mixed"] = (
    base_l11, triples(predict.predict_candidate(deleted, "L11", base_id)))

changed_u = copy.deepcopy(manifest)
changed_u["media"]["L11"]["entries"][-1]["terminal"] = 0xC7
fault_pairs["terminal_u_changed"] = (
    base_l11, triples(predict.predict_candidate(changed_u, "L11", base_id)))

base_l96 = candidates[(base_id, "L96")]
scroll_shift = signed_bodies(bodies_for(manifest, "L96", base_id), row_offset=1)
fault_pairs["scroll_one_row_shift"] = (base_l96, scroll_shift)

detected = {name for name, (good, broken) in fault_pairs.items() if broken != good}
expected_faults = {
    "one_character_replacement", "trailing_space_more", "trailing_space_less",
    "line_swap", "physical_row_shift", "four_five_per_row_swap", "type_mark_swap",
    "deleted_entry_mixed", "terminal_u_changed", "scroll_one_row_shift",
}
if detected != expected_faults:
    fail("fault_set")
ok("全故障のNG項目集合が完全一致")


# ERR 0..255 は互いに一意で、数値行から一意な判定名を得る。
error_sigs = {triples(predict.predict_error(number)) for number in range(256)}
if len(error_sigs) != 256:
    fail("error_uniqueness")
sample_run = {"entry_lines": triples(predict.predict_error(70)), "parse_class": None}
if derive._error_class(sample_run) != "files_error_err_70":
    fail("error_class")
ok("E腕ERR 0..255は一意")


# G4: summaryの欠落・重複を厳格parserが検出する。
raw = candidates_path.read_text(encoding="ascii").splitlines()
summary_index = next(i for i, line in enumerate(raw) if line.startswith("summary\t"))
missing = work / "candidates-missing.tsv"
missing.write_text("\n".join(raw[:summary_index] + raw[summary_index + 1:]) + "\n", encoding="ascii")
duplicate = work / "candidates-duplicate.tsv"
duplicate.write_text("\n".join(raw + [raw[summary_index]]) + "\n", encoding="ascii")
for label, path in (("missing", missing), ("duplicate", duplicate)):
    try:
        derive.load_candidates(path)
    except derive.InputError:
        pass
    else:
        fail("g4_" + label)
ok("G4は候補組の欠落・重複を検出")


def summary(tag):
    digest = hashlib.sha256(tag.encode("ascii")).hexdigest()
    return {"line_count": 1, "char_count": 1, "sha256": digest}


def make_run(tag, lines=(), parse_class=None):
    screen = summary(tag)
    value = {
        "screen": screen, "late_screen": dict(screen),
        "entry_lines": [{"physical_row": row, "char_count": count, "sha256": digest}
                        for row, count, digest in lines],
        "input_wait": True, "reference_unchanged": True,
        "output_audit_clean": True, "fkey_unchanged": True,
        "extra_lines_absent": True,
        "g13": {"line_sha": True, "char_count": True, "physical_row": True},
    }
    if parse_class is not None:
        value["parse_class"] = parse_class
    return value


def observations(candidate=base_id):
    arms = {}
    for arm in derive.ALL_ARMS:
        if arm in predict.LAYOUT_ARMS:
            lines = candidates[(candidate, arm)]
            run = make_run("screen-" + arm, lines)
        elif arm == "E-0":
            run = make_run("screen-E0", triples(predict.predict_error(5)))
        elif arm == "E-3":
            run = make_run("screen-E3", triples(predict.predict_error(70)))
        elif arm == "E-str":
            run = make_run("screen-Estr", (), 2)
        else:
            run = make_run("screen-" + arm)
        arms[arm] = [copy.deepcopy(run), copy.deepcopy(run)]
    arms["N-wait"][0]["input_wait"] = False
    arms["N-wait"][1]["input_wait"] = False
    return {"format": "m6fe-observations-v1", "arms": arms,
            "aux": {"order": "directory_order_skips_deleted",
                    "empty": "empty_has_no_entry_rows", "overflow": "scrolls_to_tail",
                    "drive": "default_is_1_explicit_1_2",
                    "expression": "drive_expression_accepted",
                    "no_media": "files_no_media_waits_for_media"}}


def normalized(doc):
    path = work / "obs-current.json"
    path.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")), encoding="ascii")
    return derive.load_observations(path)


positive_doc = observations()
arms, aux, input_sha = normalized(positive_doc)
derived = derive.derive(arms, aux, candidates)
derived["input_sha256"] = input_sha
if set(derived) != {"format", "overall", "gates", "candidates", "first_empty_arm",
                    "aux", "structure", "fkey_unchanged", "extra_lines_absent",
                    "input_sha256"}:
    fail("derived_allowlist")
if derived["overall"] != base_id or derived["candidates"] != [base_id]:
    fail("derive_positive")
if (derived["structure"].get("rows_per_count") != "K=5"
        or derived["structure"].get("entry_width") != "fixed_width_cell"):
    fail("derive_structure")
if derived["aux"]["errors"] != {
        "E-0": "files_error_err_5", "E-3": "files_error_err_70",
        "E-str": "files_error_parse_2"}:
    fail("derive_errors")
pack_id = base_id.replace("_G5_", "_PACK_")
pack_arms, pack_aux, _pack_sha = normalized(observations(pack_id))
pack_derived = derive.derive(pack_arms, pack_aux, candidates)
if (pack_derived["structure"].get("rows_per_count") != "K>=6"
        or pack_derived["structure"].get("entry_width") != "content_width"):
    fail("derive_structure_pack")
ok("§8.1・§8.2・§8.3の合成正例")


# G9〜G13を1つずつ壊し、偽になる関門集合を完全一致で照合する。
gate_mutations = {}
doc = observations(); doc["arms"]["L1"][1]["screen"] = summary("different"); doc["arms"]["L1"][1]["late_screen"] = summary("different")
gate_mutations["G9"] = doc
doc = observations(); doc["arms"]["L1"][0]["late_screen"] = summary("different")
gate_mutations["G10"] = doc
doc = observations(); doc["arms"]["L1"][0]["reference_unchanged"] = False
gate_mutations["G11"] = doc
doc = observations(); doc["arms"]["L1"][0]["output_audit_clean"] = False
gate_mutations["G12"] = doc
doc = observations(); doc["arms"]["L1"][0]["g13"]["line_sha"] = False
gate_mutations["G13"] = doc

for wanted, doc in gate_mutations.items():
    arms, aux, input_sha = normalized(doc)
    value = derive.derive(arms, aux, candidates)
    value["input_sha256"] = input_sha
    failed = {name for name, passed in value["gates"].items() if not passed}
    if failed != {wanted} or value["overall"] != "gate_failed":
        fail("gate_set_" + wanted)
    path = work / ("derived-" + wanted + ".json")
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii")
    proc = subprocess.run([sys.executable, str(repo / "tools" / "judge_m6fe.py"),
                           "--derived", str(path)], capture_output=True, text=True)
    if proc.returncode != 0 or json.loads(proc.stdout)["overall"] != "gate_failed":
        fail("judge_gate_" + wanted)
ok("G9〜G13の各入力を導出器・判定器が個別検出")


# 正例もjudgeが独立再計算できる。
derived_path = work / "derived-positive.json"
derived_path.write_text(json.dumps(derived, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii")
judge_proc = subprocess.run([sys.executable, str(repo / "tools" / "judge_m6fe.py"),
                             "--derived", str(derived_path)], capture_output=True, text=True)
judge_value = json.loads(judge_proc.stdout)
if (judge_proc.returncode != 0 or judge_value["overall"] != base_id
        or set(judge_value) != {"overall", "judgments", "sha256"}):
    fail("judge_positive")
judge_output = work / "judge-output.json"
judge_output.write_text(judge_proc.stdout, encoding="ascii")


# 漏えい: 合成名を含む入力から作る全出力と、例外経路のstdout/stderrを監査。
leak_manifest = copy.deepcopy(manifest)
leak_manifest["media"]["L1"]["entries"][0]["name"] = canary
leak_manifest_path = work / "leak-manifest.json"
leak_manifest_path.write_text(json.dumps(leak_manifest, sort_keys=True), encoding="ascii")
leak_candidates = work / "leak-candidates.tsv"
leak_errors = work / "leak-errors.tsv"
predict_out = work / "predict.out"
predict_err = work / "predict.err"
with predict_out.open("w") as out, predict_err.open("w") as err:
    proc = subprocess.run([sys.executable, str(repo / "tools" / "predict_m6fe.py"),
                           str(leak_manifest_path), "--output", str(leak_candidates)],
                          stdout=out, stderr=err)
if proc.returncode != 0:
    fail("leak_predict")
subprocess.run([sys.executable, str(repo / "tools" / "predict_m6fe.py"),
                str(leak_manifest_path), "--output", str(leak_errors),
                "--errors-for-arm", "E-0"], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

bad_obs = work / "bad-observation.json"
bad_obs.write_text(json.dumps({"format": "m6fe-observations-v1", "arms": {},
                               "aux": {}, "forbidden": canary}), encoding="ascii")
bad_out = work / "bad.out"; bad_err = work / "bad.err"
with bad_out.open("w") as out, bad_err.open("w") as err:
    subprocess.run([sys.executable, str(repo / "tools" / "derive_m6fe.py"),
                    "--observations", str(bad_obs)], stdout=out, stderr=err)

audit = [leak_candidates, leak_errors, predict_out, predict_err, derived_path,
         judge_output, work / "g4.out", work / "g4.err", bad_out, bad_err]
audit.extend(work.glob("derived-G*.json"))
for path in audit:
    if canary.encode("ascii") in path.read_bytes():
        fail("leak_output")
ok("漏えい目印は期待TSV・判定JSON・stdout/stderr・例外経路に無い")

# 陰性対照: 本文列を故意に作ると同じ監査で必ず検出する。
broken = work / "broken-output.tsv"
broken.write_text("body\t" + canary + "\n", encoding="ascii")
if canary.encode("ascii") not in broken.read_bytes():
    fail("leak_negative_control")
ok("漏えい監査の陰性対照")
PY

printf '%s\n' 'OK m6f-e器具C 全項目合格'
