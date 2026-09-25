#!/usr/bin/env python3
"""m6f-d の測定結果(result JSON)と保存済み媒体(raw-dir/ARM-rN.d88)から、
事前登録 docs/notes/m6f-d-disk-rules-preregistration.md 第5節の D1〜D9 を
機械導出する。

割り当て表の位置160以降・本体セクタの中身は、内部でも読まない設計にする
（事前登録 §0.1）。D1〜D4 が使う P は「位置0〜159のうち T[k]≠0xFF」のみに
限定し（§5冒頭の定義）、m6f-cのderive_m6fc.py（changed_positionsはfree markの
値v_starとの差分を256バイト全域で見る）とは別の絞り込みをここで新たに行う。
一方、単位の探索・鎖の検証・終端の分類・先頭単位欄の候補探索そのものの
アルゴリズムはderive_m6fc.pyのunit_mapping/chain/terminal_rule/
entry_head_fieldをそのまま再利用する（事前登録が「m6f-c C4/C5/C6/C7と同じ」
と明記しているため、二重実装を避ける）。

解釈を加えた点（事前登録の文言に明示が無かったため、このセッションで
固定した約束事。報告に転記する）:
  - D3の e・u は、腕ごとに「その腕自身が持つ単位の対応(S,o)」で鎖をたどって
    得た終端値と、D1(I-250由来の全域S,o)で決めた最後の単位の線形範囲に
    含まれる書き込みセクタ数、の組み合わせで求める。範囲の算出にD1の(S,o)を
    使うのはm6f-c C6と同じ流儀（A3固有のS,oを全腕の範囲算出に使う）。
  - D4(先頭単位の欄)は腕ごとに独立に単位の対応を求め直す（m6f-c C7と同じ。
    D1のderived判定には依存しない——C7もC4のderived判定を前提にしない）。
  - D7の「先頭単位の欄」の位置は、D4がderivedならその位置(0始まり)、
    でなければ10。entry_fieldsのbytes9_15はオフセット9〜15の7要素なので、
    参照するインデックスは (位置-9)。
  - 総合判定(§7)の「D1〜D4がderived」: D2(鎖)はderive_m6fc.chain()と同じ構造で
    status文字列が"link_is_next_index"/"link_other"であり"derived"を持たない。
    ここではH2の鎖の規則が確認できたこと(status=="link_is_next_index"、
    不一致0件)を「derived」とみなす。D3は"end_constant"/"end_plus_used_sectors"/
    "end_other"のいずれかであれば「derived」とみなす(m6f-c C6も同型)。
  - r_star(result, raw_dir=None): raw_dir省略時は環境変数 M6FD_RAW_DIR から
    読む（測定ドライバがderive_m6fd.r_star(result)を1引数で呼ぶ前提のため。
    どちらも無ければ InputError）。
  - 事前登録 §5末尾の「2走で結果が一致しない導出はambiguous」は、D1〜D4だけ
    でなくD5〜D9の腕別判定（II-d等・III-*・IV-*・V-*の個々の腕の2走一致）にも
    同様に適用する（腕別の判定名がグローバルな規則の一部であるため）。

導出器自身は本体セクタの中身・割り当て表の位置160以降の値を標準出力へ
出さない。出すのは座標・位置・事前登録で導出と定めた値だけ。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive_m6fc as dm  # noqa: E402
from d88_read_sector import D88Error  # noqa: E402

I_ARMS = ("I-250", "I-1", "I-3", "I-6", "I-10", "I-17")
ENTRY_NAME_QZ7B = b"QZ7B"
ENTRY_NAME_QZ7A = b"QZ7A"
V_ARMS = ("V-missing", "V-crc", "V-deleted", "V-single", "V-ff", "V-c9")
V_BOOT_ARMS = ("V-missing", "V-crc", "V-deleted", "V-single")

FAT_PRIMARY = dm.FAT_PRIMARY  # (18,1,14)
FAT_REPLICAS = ((18, 1, 15), (18, 1, 16))


class InputError(ValueError):
    pass


# --- 共通: markers ------------------------------------------------------

def _tags(run: dict[str, Any]) -> set[str]:
    return {m["tag"] for m in run.get("markers", [])}


def _has_marker(run: dict[str, Any] | None, tag: str, numbers: list[int] | None = None) -> bool:
    if run is None:
        return False
    for m in run.get("markers", []):
        if m["tag"] == tag and (numbers is None or m.get("numbers") == numbers):
            return True
    return False


def _both_runs(runs_by_key: dict[tuple[str, int], dict[str, Any]], arm: str, pred) -> bool:
    r1, r2 = runs_by_key.get((arm, 1)), runs_by_key.get((arm, 2))
    return r1 is not None and r2 is not None and pred(r1) and pred(r2)


# --- 媒体側: 位置0〜159限定のP -----------------------------------------------

def p_positions_m6fd(reader) -> set[int]:
    """P = { k : 0<=k<=159, T[k] != 0xFF }。位置160以降は読まない。"""
    payload = dm.sector(reader, FAT_PRIMARY)
    return {i for i in range(160) if payload[i] != 0xFF}


def replicas_match_0_159(reader, coord: tuple[int, int, int], t_bytes: bytes) -> bool:
    payload = dm.sector(reader, coord)
    return all(payload[i] == t_bytes[i] for i in range(160))


def units_in_order(body_linear: list[int], s: int, o: int) -> list[int]:
    """本体のセクタ（ファイル内の順）を単位の番号の列にする。連続する同じ番号は1つにまとめる
    （セクタごとの列のままだと同じ単位どうしを鎖として比べてしまう。m6f-c の導出器の不具合）。"""
    out: list[int] = []
    for number in body_linear:
        k = (number - o) // s
        if not out or out[-1] != k:
            out.append(k)
    return out


def per_arm_rep(reader, forced: tuple[int, int] | None = None) -> dict[str, Any]:
    """1走ぶんのD1〜D4材料(位置0〜159限定)。forced=(S,o) を与えたら、腕ごとの対応ではなく
    D1（I-250）で決めた対応を使う（事前登録 §5 D3・D4 は「D1 が derived のとき」）。"""
    body = dm.find_body_sectors(reader)
    body_linear = [dm.linear_number(*coord) for coord, _num in body]
    p_positions = p_positions_m6fd(reader)
    mapping = dm.unit_mapping(p_positions, body_linear)
    t_bytes = dm.sector(reader, FAT_PRIMARY)
    k_sequence: list[int] = []
    chain_result: dict[str, Any] | None = None
    so = forced if forced is not None else (
        (mapping["value"]["s"], mapping["value"]["o"]) if mapping["status"] == "derived" else None)
    if so is not None and body_linear:
        k_sequence = units_in_order(body_linear, so[0], so[1])
        chain_result = dm.chain(t_bytes, k_sequence)
    entry_hits = dm.find_name(reader, ENTRY_NAME_QZ7B, dm.TRACK18_NON_FAT_COORDS)
    entry_head_matches: list[int] = []
    if k_sequence and entry_hits:
        union: set[int] = set()
        for hit in entry_hits:
            union |= set(dm.entry_head_field(reader, hit, k_sequence[0]))
        entry_head_matches = sorted(union)
    return {
        "body_linear": body_linear,
        "p_positions": sorted(p_positions),
        "unit_mapping": mapping,
        "k_sequence": k_sequence,
        "chain": chain_result,
        "entry_hits": entry_hits,
        "entry_head_matches": entry_head_matches,
        "replica15_matches_t": replicas_match_0_159(reader, FAT_REPLICAS[0], t_bytes),
        "replica16_matches_t": replicas_match_0_159(reader, FAT_REPLICAS[1], t_bytes),
    }


def _consensus_rep(reps: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    if any(r is None for r in reps):
        return None
    key0 = json.dumps(reps[0], sort_keys=True, separators=(",", ":"))
    key1 = json.dumps(reps[1], sort_keys=True, separators=(",", ":"))
    return reps[0] if key0 == key1 else None


def load_i_reps(raw_dir: Path) -> dict[str, list[dict[str, Any] | None]]:
    """I-250 で D1 の対応を決め、他の I-* にはその対応を与えて読む。"""
    reps = {"I-250": _load_arm_reps(raw_dir, "I-250")}
    d1 = d1_unit_and_position(reps)
    forced = (d1["value"]["s"], d1["value"]["o"]) if d1.get("status") == "derived" else None
    for arm in I_ARMS:
        if arm != "I-250":
            reps[arm] = _load_arm_reps(raw_dir, arm, forced)
    return reps


def _load_arm_reps(raw_dir: Path, arm: str, forced: tuple[int, int] | None = None) -> list[dict[str, Any] | None]:
    reps: list[dict[str, Any] | None] = []
    for rep in (1, 2):
        path = raw_dir / f"{arm}-r{rep}.d88"
        if not path.exists():
            reps.append(None)
            continue
        try:
            reader = dm.load_disk(path)
            reps.append(per_arm_rep(reader, forced))
        except (dm.InputError, D88Error):
            reps.append(None)
    return reps


def write_count_in_range(run: dict[str, Any] | None, lo: int, hi: int) -> int:
    return dm.write_count_in_range(run, lo, hi)


# --- D1 単位と位置 -----------------------------------------------------------

def d1_unit_and_position(per_arm_reps: dict[str, list[dict[str, Any] | None]]) -> dict[str, Any]:
    i250 = _consensus_rep(per_arm_reps.get("I-250", [None, None]))
    if i250 is None:
        return {"status": "ambiguous", "candidate_count": 2}
    out = dict(i250["unit_mapping"])
    out["replica_15_matches_t"] = i250["replica15_matches_t"]
    out["replica_16_matches_t"] = i250["replica16_matches_t"]
    return out


# --- D2 鎖 --------------------------------------------------------------------

def d2_chain(d1: dict[str, Any], per_arm_reps: dict[str, list[dict[str, Any] | None]]) -> dict[str, Any] | None:
    if d1.get("status") != "derived":
        return {"status": "not_found", "candidate_count": 0}
    i250 = _consensus_rep(per_arm_reps.get("I-250", [None, None]))
    if i250 is None or i250["chain"] is None:
        return {"status": "not_found", "candidate_count": 0}
    return i250["chain"]


# --- D3 終端 -------------------------------------------------------------------

def d3_terminal(d1: dict[str, Any], per_arm_reps: dict[str, list[dict[str, Any] | None]],
                 runs_by_key: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    if d1.get("status") != "derived":
        return {"status": "not_found", "candidate_count": 0}
    s, o = d1["value"]["s"], d1["value"]["o"]
    entries: dict[str, dict[str, Any]] = {}
    for arm in I_ARMS:
        reps = per_arm_reps.get(arm, [None, None])
        consensus = _consensus_rep(reps)
        if consensus is None or consensus["chain"] is None:
            continue
        e = consensus["chain"]["terminal_value"]
        k_last = consensus["chain"]["k_sequence"][-1]
        lo, hi = k_last * s + o, k_last * s + o + s
        u1 = write_count_in_range(runs_by_key.get((arm, 1)), lo, hi)
        u2 = write_count_in_range(runs_by_key.get((arm, 2)), lo, hi)
        if u1 != u2:
            continue
        entries[arm] = {"e": e, "u": u1}
    if len(entries) != len(I_ARMS):
        return {"status": "not_found", "candidate_count": 0, "detail": entries}
    return dm.terminal_rule(entries)


# --- D4 先頭単位の欄 -----------------------------------------------------------

def d4_entry_head_field(per_arm_reps: dict[str, list[dict[str, Any] | None]]) -> dict[str, Any]:
    candidate_j: set[int] | None = None
    detail: dict[str, list[int]] = {}
    ok = True
    for arm in I_ARMS:
        reps = per_arm_reps.get(arm, [None, None])
        if any(r is None for r in reps):
            ok = False
            break
        if reps[0]["entry_head_matches"] != reps[1]["entry_head_matches"]:
            ok = False
            break
        matches = set(reps[0]["entry_head_matches"])
        detail[arm] = sorted(matches)
        candidate_j = matches if candidate_j is None else (candidate_j & matches)
    if ok and candidate_j:
        out = dm._result([{"offset": j} for j in sorted(candidate_j)])
        out["detail"] = detail
        return out
    return {"status": "not_found", "candidate_count": 0, "detail": detail}


# --- D5 付け替えの読み込み ------------------------------------------------------

def d5_relocated_readable(runs_by_key: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    ii_d_ok = _both_runs(runs_by_key, "II-d", lambda r: _has_marker(r, "rb", [0]))
    ii_p_ok = _both_runs(runs_by_key, "II-p", lambda r: _has_marker(r, "ld"))
    neg1_failed = _both_runs(runs_by_key, "II-neg1", lambda r: _has_marker(r, "rb", [0]))
    neg2_failed = _both_runs(runs_by_key, "II-neg2", lambda r: _has_marker(r, "rb", [0]))
    if neg1_failed or neg2_failed:
        return {"status": "control_failed", "ii_neg1_rb0": neg1_failed, "ii_neg2_rb0": neg2_failed}
    if ii_d_ok and ii_p_ok:
        return {"status": "relocated_readable"}
    return {"status": "not_readable", "ii_d_ok": ii_d_ok, "ii_p_ok": ii_p_ok}


# --- D6 ディレクトリの広がり -----------------------------------------------------

def _tag_status(run: dict[str, Any] | None) -> str | None:
    if run is None:
        return None
    tags = _tags(run)
    for t in ("ok", "ng", "er"):
        if t in tags:
            return t
    return "none"


def _arm_status(runs_by_key: dict[tuple[str, int], dict[str, Any]], arm: str) -> str | None:
    r1, r2 = runs_by_key.get((arm, 1)), runs_by_key.get((arm, 2))
    if r1 is None or r2 is None:
        return None
    s1, s2 = _tag_status(r1), _tag_status(r2)
    return s1 if s1 == s2 else None


def d6_directory_extent(runs_by_key: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    zero_found: set[int] = set()
    ff_found: set[int] = set()
    for r in range(1, 13):
        if _arm_status(runs_by_key, f"III-00-{r:02d}") == "ok":
            zero_found.add(r)
        if _arm_status(runs_by_key, f"III-FF-{r:02d}") == "ok":
            ff_found.add(r)
    none_status = _arm_status(runs_by_key, "III-none")
    if none_status != "er":
        return {"status": "control_failed", "none_status": none_status}
    stops_at = sorted(zero_found - ff_found)
    return {
        "status": "stops_at_unused" if stops_at else "scans_past_unused",
        "directory_sectors": sorted(zero_found),
        "found_with_ff": sorted(ff_found),
        "stops_at": stops_at,
    }


# --- D7 使用中とみなす値 ---------------------------------------------------------

def _entry_head_position(d4: dict[str, Any]) -> int:
    if d4.get("status") == "derived":
        return d4["value"]["offset"]
    return 10


def d7_reserved_value(runs_by_key: dict[tuple[str, int], dict[str, Any]], d4: dict[str, Any]) -> dict[str, Any]:
    pos = _entry_head_position(d4)
    idx = pos - 9
    rused: list[int] = []
    for r_value in range(256):
        arm = f"IV-R-{r_value:02X}"

        def _ok(run: dict[str, Any], idx=idx) -> bool:
            if not _has_marker(run, "ok"):
                return False
            ef = (run.get("entry_fields") or {}).get("QZ7A")
            if not ef or "bytes9_15" not in ef:
                return False
            bytes9_15 = ef["bytes9_15"]
            if not (0 <= idx < len(bytes9_15)):
                return False
            return bytes9_15[idx] == 20

        if _both_runs(runs_by_key, arm, _ok):
            rused.append(r_value)
    control_failed = 0xFF in rused
    return {"rused": sorted(rused), "control_failed": control_failed, "pos_offset": pos}


def r_star(result: dict[str, Any], raw_dir: Path | str | None = None) -> int | None:
    """§5 D7のR*。raw_dir省略時は環境変数 M6FD_RAW_DIR から読む
    （測定ドライバが derive_m6fd.r_star(result) を1引数で呼ぶ前提のため）。"""
    if raw_dir is None:
        env = os.environ.get("M6FD_RAW_DIR")
        if not env:
            raise InputError("raw_dir が指定されておらず、環境変数 M6FD_RAW_DIR も未設定")
        raw_dir = env
    raw_dir = Path(raw_dir)
    runs_by_key = {(r["arm"], r["repetition"]): r for r in result.get("runs", [])}
    per_arm_reps = load_i_reps(raw_dir)
    d1 = d1_unit_and_position(per_arm_reps)
    d3 = d3_terminal(d1, per_arm_reps, runs_by_key)
    d4 = d4_entry_head_field(per_arm_reps)
    d7 = d7_reserved_value(runs_by_key, d4)
    rused = d7["rused"]
    if not rused:
        return None
    detail = d3.get("detail") if isinstance(d3, dict) else None
    es_observed = {v["e"] for v in detail.values()} if isinstance(detail, dict) else set()
    candidates = [r for r in rused if 0xA0 <= r <= 0xFE and r not in es_observed]
    if candidates:
        return min(candidates)
    return min(rused)


# --- D8 予約の印の要否 -----------------------------------------------------------

def _ck_state(run: dict[str, Any] | None) -> str | None:
    if run is None:
        return None
    if _has_marker(run, "ck", [1]):
        return "ck1"
    if _has_marker(run, "ck", [0]):
        return "ck0"
    if any(m["tag"] == "cx" for m in run.get("markers", [])):
        return "cx"
    return "other"


def _fe_detail(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if run is None:
        return None
    for m in run.get("markers", []):
        if m["tag"] == "fe":
            numbers = m.get("numbers", [])
            return {"err": numbers[0] if len(numbers) > 0 else None,
                    "n": numbers[1] if len(numbers) > 1 else None}
    return None


def d8_reserve_needed(runs_by_key: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    def arm_state(arm: str) -> str:
        r1, r2 = runs_by_key.get((arm, 1)), runs_by_key.get((arm, 2))
        s1, s2 = _ck_state(r1), _ck_state(r2)
        if s1 is None or s2 is None:
            return "not_found"
        return s1 if s1 == s2 else "ambiguous"

    free_state = arm_state("IV-fill-free")
    res_state = arm_state("IV-fill-res")
    detail = {
        "free": free_state, "res": res_state,
        "free_fe": [_fe_detail(runs_by_key.get(("IV-fill-free", rep))) for rep in (1, 2)],
        "res_fe": [_fe_detail(runs_by_key.get(("IV-fill-res", rep))) for rep in (1, 2)],
    }
    if free_state == "ambiguous" or res_state == "ambiguous":
        return {"status": "ambiguous", **detail}
    if free_state in ("cx", "ck0") and res_state == "ck1":
        return {"status": "reserve_needed", **detail}
    if free_state == "ck1" and res_state == "ck1":
        return {"status": "reserve_not_needed", **detail}
    return {"status": "reserve_other", **detail}


# --- D9 起動 ----------------------------------------------------------------------

def _classify_v_run(run: dict[str, Any] | None) -> str | None:
    if run is None:
        return None
    tags = _tags(run)
    if "bt" not in tags:
        return "no_basic"
    if "ok" in tags:
        return "disk_basic"
    if "er" in tags:
        return "error_after_boot"
    return "nondisk_basic"


def d9_boot(runs_by_key: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    classes: dict[str, str] = {}
    for arm in V_ARMS:
        r1, r2 = runs_by_key.get((arm, 1)), runs_by_key.get((arm, 2))
        c1, c2 = _classify_v_run(r1), _classify_v_run(r2)
        if c1 is None or c2 is None:
            classes[arm] = "not_found"
        else:
            classes[arm] = c1 if c1 == c2 else "ambiguous"
    disk_basic_arms = sorted(a for a in V_BOOT_ARMS if classes[a] == "disk_basic")
    control_changed = classes.get("V-ff") != "no_basic" or classes.get("V-c9") != "nondisk_basic"
    return {"classes": classes, "disk_basic_arms": disk_basic_arms, "control_changed": control_changed}


# --- 統合 ----------------------------------------------------------------------

def build(result: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    runs_by_key = {(r["arm"], r["repetition"]): r for r in result.get("runs", [])}
    per_arm_reps = load_i_reps(raw_dir)

    out: dict[str, Any] = {}
    out["D1"] = d1_unit_and_position(per_arm_reps)
    out["D2"] = d2_chain(out["D1"], per_arm_reps)
    out["D3"] = d3_terminal(out["D1"], per_arm_reps, runs_by_key)
    out["D4"] = d4_entry_head_field(per_arm_reps)
    out["D5"] = d5_relocated_readable(runs_by_key)
    out["D6"] = d6_directory_extent(runs_by_key)
    out["D7"] = d7_reserved_value(runs_by_key, out["D4"])
    out["D8"] = d8_reserve_needed(runs_by_key)
    out["D9"] = d9_boot(runs_by_key)

    # D2(鎖)はderive_m6fc.chain()と同じ構造で、statusは"link_is_next_index"/
    # "link_other"（"derived"という文字列は持たない）。ここでの「derived」は
    # H2の鎖の規則が確認できたこと、すなわちlink_is_next_index(不一致0件)を指す。
    core_derived = (out["D1"].get("status") == "derived"
                    and out["D2"] is not None and out["D2"].get("status") == "link_is_next_index"
                    # end_other は「終端の規則が見つからない」なので derived に数えない。
                    and out["D3"].get("status") in ("end_constant", "end_plus_used_sectors")
                    and out["D4"].get("status") == "derived")
    d6_ok = out["D6"].get("status") in ("stops_at_unused", "scans_past_unused") \
        and len(out["D6"].get("directory_sectors", [])) >= 1
    overall = "m6f_d_rules_confirmed" if (
        core_derived and out["D5"].get("status") == "relocated_readable" and d6_ok
    ) else "m6f_d_incomplete"

    return {"schema": 1, "derivations": out, "overall": overall}


def load_result(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise InputError("結果JSONの形式")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True, type=Path)
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        result = load_result(args.result)
        body = build(result, args.raw_dir)
        digest = hashlib.sha256(args.result.read_bytes()).hexdigest()
        body["input_sha256"] = digest
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
