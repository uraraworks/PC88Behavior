#!/usr/bin/env python3
"""m6f-d 追補1(docs/notes/m6f-d-addendum1-terminal-and-reserve.md)の導出器。

入力:
  - base_derived: tools/derive_m6fd.py が本編の(包み直した)2回目の結果から
    出した derivations（D1・D2・D4・D5・D6 をそのまま使う。D3・D7・D8は
    本追補の値で置き換える）。
  - base_result_rewrapped: tools/m6fd_rewrap_add1.py で包み直した本編2回目の
    result.json（D7' の再導出、および事後記録用のI-*6腕に使う）。
  - base_raw_dir: 本編2回目の raw-dir（I-*6腕の像 I-n-rR.d88 がある）。
  - add1_result: tools/measure_m6fd_add1.sh の結果（E-*6腕の判定に使う）。
  - add1_raw_dir: 追補1の raw-dir（E-n-rR.d88 がある）。

D3'（終端の規則の前向きの確認、追補1 §3.1）:
  エントリ(QZ7B)の10バイト目(0始まりのentry[10])を先頭k1とし、
  T[k]<160のあいだTをたどる。最初にT[k]>=160となった単位を最後の単位k_m、
  その値をeとする。T[k]==0xFFに当たる・160未満のまま一周する・k1が
  範囲外、のいずれかは chain_broken とする。uは、装置番号1のWRITE DATAの
  座標のうち線形番号が8k_m〜8k_m+7のものの数(重複は1つ)。

  6腕すべてでe-uが同じ値ならend_plus_used_sectors、6腕のeが同じなら
  end_constant、どちらでもない(chain_brokenの腕を含む)場合はend_other。

R*: derive_m6fd.d7_reserved_value(D4は10固定)で導出し直したD7'から、
本編事前登録§5 D7の規則でR*を決める。ただし「D3で観測した終端の値」は、
本編2回目のI-*6腕にD3'を当てた(事後の記録)e の集合を使う。

D8: 追補1で回したIV-fill-free/IV-fill-resに derive_m6fd.d8_reserve_needed
をそのまま当てる(タグの意味は本編と同じ)。

導出器自身は本体セクタの中身・割り当て表の位置160以降の値を標準出力へ
出さない(m6f-d事前登録§0.1・G9)。内部でセクタ全体を読み込むことはあるが
(既存のderive_m6fc/derive_m6fdと同じ流儀)、出力するのは座標・位置0〜159の
値・事前登録で導出と定めた値だけ。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive_m6fc as dm  # noqa: E402
import derive_m6fd as dfd  # noqa: E402
from d88_read_sector import D88Error  # noqa: E402

E_ARMS = ("E-2", "E-4", "E-8", "E-12", "E-20", "E-33")
ENTRY_NAME_QZ7B = "QZ7B"
FAT_PRIMARY = dm.FAT_PRIMARY  # (18,1,14)


class InputError(ValueError):
    pass


# --- D3'(終端の規則の前向きの確認) -------------------------------------------

def _follow_chain(t_bytes: bytes, k1: int) -> dict[str, Any]:
    """T[0..159]だけを読んでk1から鎖をたどる。位置160以降は一切読まない。"""
    if not (0 <= k1 <= 159):
        return {"status": "chain_broken", "reason": "out_of_range"}
    seen: list[int] = []
    seen_set: set[int] = set()
    k = k1
    while True:
        if k in seen_set:
            return {"status": "chain_broken", "reason": "loop", "k_sequence": seen}
        seen_set.add(k)
        seen.append(k)
        v = t_bytes[k]
        if v < 160:
            k = v
            continue
        if v == 0xFF:
            return {"status": "chain_broken", "reason": "hits_ff", "k_sequence": seen}
        return {"status": "ok", "k_last": k, "e": v, "k_sequence": seen}


def _arm_rep_d3_prime(run: dict[str, Any] | None, image_path: Path,
                       entry_name: str) -> dict[str, Any] | None:
    if run is None or not image_path.exists():
        return None
    ef = (run.get("entry_fields") or {}).get(entry_name)
    if not ef or "bytes9_15" not in ef:
        return None
    bytes9_15 = ef["bytes9_15"]
    if len(bytes9_15) < 2:
        return None
    k1 = bytes9_15[1]  # offset10 = entry[10] = "10バイト目"
    try:
        reader = dm.load_disk(image_path)
        t_bytes = dm.sector(reader, FAT_PRIMARY)
    except (dm.InputError, D88Error):
        return {"status": "chain_broken", "reason": "read_error"}
    chain = _follow_chain(t_bytes, k1)
    if chain["status"] != "ok":
        return chain
    k_m, e = chain["k_last"], chain["e"]
    lo, hi = 8 * k_m, 8 * k_m + 8
    u = dm.write_count_in_range(run, lo, hi)
    return {"status": "ok", "e": e, "u": u, "k_last": k_m}


def _arm_d3_prime(runs_by_key: dict[tuple[str, int], dict[str, Any]], raw_dir: Path,
                   arm: str, entry_name: str) -> dict[str, Any]:
    r1 = _arm_rep_d3_prime(runs_by_key.get((arm, 1)), raw_dir / f"{arm}-r1.d88", entry_name)
    r2 = _arm_rep_d3_prime(runs_by_key.get((arm, 2)), raw_dir / f"{arm}-r2.d88", entry_name)
    if r1 is None or r2 is None:
        return {"status": "not_found"}
    if r1["status"] != "ok" or r2["status"] != "ok":
        return {"status": "chain_broken"}
    if (r1["e"], r1["u"]) != (r2["e"], r2["u"]):
        return {"status": "ambiguous", "rep1": r1, "rep2": r2}
    return {"status": "ok", "e": r1["e"], "u": r1["u"]}


def d3_prime(runs_by_key: dict[tuple[str, int], dict[str, Any]], raw_dir: Path,
             arms: tuple[str, ...], entry_name: str = ENTRY_NAME_QZ7B) -> dict[str, Any]:
    """追補1 §3.1 D3'。armsに渡した腕の集合について判定する
    (E-*なら判定に使う本体、I-*なら事後の記録)。"""
    entries: dict[str, dict[str, Any]] = {}
    broken: list[str] = []
    other: dict[str, str] = {}
    for arm in arms:
        res = _arm_d3_prime(runs_by_key, raw_dir, arm, entry_name)
        status = res["status"]
        if status == "ok":
            entries[arm] = {"e": res["e"], "u": res["u"]}
        elif status == "chain_broken":
            broken.append(arm)
        else:
            other[arm] = status
    if broken or other or len(entries) != len(arms):
        return {"status": "end_other", "detail": entries, "chain_broken_arms": sorted(broken),
                "other_arms": other}
    result = dm.terminal_rule(entries)
    if result["status"] == "end_plus_used_sectors":
        result["matches_expected_0xc0"] = result.get("value") == 0xC0
    result["chain_broken_arms"] = []
    return result


# --- D7'(R*の導出し直し)・D8 --------------------------------------------------

def d7_prime(base_result_rewrapped: dict[str, Any]) -> dict[str, Any]:
    runs_by_key = {(r["arm"], r["repetition"]): r for r in base_result_rewrapped.get("runs", [])}
    return dfd.d7_reserved_value(runs_by_key, {"status": "not_found"})  # D4=10固定


def r_star_add1(base_result_rewrapped: dict[str, Any], base_raw_dir: Path) -> tuple[int | None, dict[str, Any]]:
    d7p = d7_prime(base_result_rewrapped)
    rused = d7p["rused"]
    runs_by_key = {(r["arm"], r["repetition"]): r for r in base_result_rewrapped.get("runs", [])}
    i_d3p = d3_prime(runs_by_key, base_raw_dir, dfd.I_ARMS)
    if not rused:
        return None, d7p
    detail = i_d3p.get("detail") if isinstance(i_d3p, dict) else None
    es_observed = {v["e"] for v in detail.values()} if isinstance(detail, dict) else set()
    candidates = [r for r in rused if 0xA0 <= r <= 0xFE and r not in es_observed]
    return (min(candidates) if candidates else min(rused)), d7p


def d8_add1(add1_result: dict[str, Any]) -> dict[str, Any]:
    runs_by_key = {(r["arm"], r["repetition"]): r for r in add1_result.get("runs", [])}
    return dfd.d8_reserve_needed(runs_by_key)


# --- 統合 ----------------------------------------------------------------------

def build(base_derived: dict[str, Any], base_result_rewrapped: dict[str, Any], base_raw_dir: Path,
          add1_result: dict[str, Any], add1_raw_dir: Path) -> dict[str, Any]:
    base_d = base_derived.get("derivations", {})
    runs_by_key_add1 = {(r["arm"], r["repetition"]): r for r in add1_result.get("runs", [])}
    d3_prime_result = d3_prime(runs_by_key_add1, add1_raw_dir, E_ARMS)
    d7_prime_result = d7_prime(base_result_rewrapped)
    d8_result = d8_add1(add1_result)
    r_star_value, _ = r_star_add1(base_result_rewrapped, base_raw_dir)
    runs_by_key_base = {(r["arm"], r["repetition"]): r for r in base_result_rewrapped.get("runs", [])}
    i_d3_prime_posthoc = d3_prime(runs_by_key_base, base_raw_dir, dfd.I_ARMS)

    d1, d2, d4 = base_d.get("D1", {}), base_d.get("D2", {}), base_d.get("D4", {})
    core_derived = (d1.get("status") == "derived"
                    and d2.get("status") == "link_is_next_index"
                    and d3_prime_result.get("status") in ("end_constant", "end_plus_used_sectors")
                    and d4.get("status") == "derived")
    d5, d6 = base_d.get("D5", {}), base_d.get("D6", {})
    d5_ok = d5.get("status") == "relocated_readable"
    d6_ok = (d6.get("status") in ("stops_at_unused", "scans_past_unused")
             and len(d6.get("directory_sectors", [])) >= 1)
    overall = "m6f_d_add1_rules_confirmed" if (core_derived and d5_ok and d6_ok) else "m6f_d_add1_incomplete"

    return {
        "schema": 1,
        "derivations": {
            "D1": d1, "D2": d2, "D3_prime": d3_prime_result, "D4": d4, "D5": d5, "D6": d6,
            "D7_prime": d7_prime_result, "D8": d8_result,
            "I_D3_prime_posthoc": i_d3_prime_posthoc,
        },
        "r_star": r_star_value,
        "overall": overall,
    }


def load_json(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise InputError(f"JSON形式が不正: {path}")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-derived", required=True, type=Path)
    ap.add_argument("--base-result", required=True, type=Path, help="包み直し済みの本編2回目のresult.json")
    ap.add_argument("--base-raw-dir", required=True, type=Path)
    ap.add_argument("--add1-result", required=True, type=Path)
    ap.add_argument("--add1-raw-dir", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        base_derived = load_json(args.base_derived)
        base_result = load_json(args.base_result)
        add1_result = load_json(args.add1_result)
        body = build(base_derived, base_result, args.base_raw_dir, add1_result, args.add1_raw_dir)
        digest = hashlib.sha256(args.add1_result.read_bytes()).hexdigest()
        body["add1_input_sha256"] = digest
        text = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
