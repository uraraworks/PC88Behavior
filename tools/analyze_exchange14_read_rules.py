#!/usr/bin/env python3
"""交換#14の要求位置・FDC結果・5回のREAD DATA位置対応を値なしで集計する。

生ログ中の値は比較器内部だけで扱い、標準出力には位置番号、一致件数、
FDCの公開アドレッシング規則に対する成立件数だけを出す。値そのものは
正常系・異常系とも出力しない。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_boot_exchange as boot  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402


PARAM_COUNTS = {
    0x02: 8, 0x03: 2, 0x04: 1, 0x05: 8, 0x06: 8, 0x07: 1,
    0x08: 0, 0x09: 8, 0x0A: 1, 0x0C: 8, 0x0D: 5, 0x0F: 2,
    0x11: 8, 0x19: 8, 0x1D: 8,
}
NO_RESULT = {0x03, 0x07, 0x0F}


class SafeError(Exception):
    pass


@dataclass
class Command:
    opcode: int
    params: list[int]
    inputs: list[int]
    clock: int

    def __repr__(self) -> str:
        return "Command(<redacted>)"


def need(v: int | None) -> int:
    if v is None:
        raise SafeError("伏せ字ログでは位置対応を測定できない")
    return v


def commands(rows: list[m2s.Ev], lo: int, hi: int) -> list[Command]:
    fb = [e for e in rows if e.cpu == "sub" and e.port == "00FB" and lo <= e.clock < hi]
    out: list[Command] = []
    i = 0
    while i < len(fb):
        if fb[i].kind != "OUT":
            i += 1
            continue
        first = fb[i]
        opcode = need(first.value) & 0x1F
        nparam = PARAM_COUNTS.get(opcode)
        if nparam is None:
            raise SafeError("公開FDCコマンド表に無いコマンドを検出")
        if i + nparam >= len(fb):
            raise SafeError("FDCコマンドのパラメータが不足")
        params: list[int] = []
        for j in range(1, nparam + 1):
            if fb[i + j].kind != "OUT":
                raise SafeError("FDCコマンドのパラメータ途中で方向が変化")
            params.append(need(fb[i + j].value))
        i += nparam + 1
        inputs: list[int] = []
        if opcode not in NO_RESULT:
            while i < len(fb) and fb[i].kind == "IN":
                inputs.append(need(fb[i].value))
                i += 1
        out.append(Command(opcode, params, inputs, first.clock))
    return out


def latest_before(cmds: list[Command], index: int, opcode: int) -> Command | None:
    for c in reversed(cmds[:index]):
        if c.opcode == opcode:
            return c
    return None


def matches(source: list[int], reads: list[Command], p: int) -> list[int]:
    return [sum(v == r.params[p] for v, r in zip(source, reads))]


def vector(source: list[int], reads: list[Command], p: int) -> str:
    bits = ["1" if v == r.params[p] else "0" for v, r in zip(source, reads)]
    return "".join(bits) + f" ({sum(b == '1' for b in bits)}/5)"


def prefix_len(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def fold_sum(xs: list[int]) -> int:
    return sum(xs) & 0xFF


def fold_xor(xs: list[int]) -> int:
    out = 0
    for x in xs:
        out ^= x
    return out


def extract(rows: list[m2s.Ev]) -> tuple[list[int], list[int], list[int], list[Command]]:
    tx = m2s.classify_transactions(rows)
    runs = boot.group_runs(tx)
    _, bulk_run = boot.split_boot_and_bulk(runs)
    pairs = boot.pair_rounds(runs)
    if len(pairs) < 15 or bulk_run is None:
        raise SafeError("交換#14または公式バルク区間を特定できない")
    req_run, response_run = pairs[14]
    if len(req_run.events) != 12:
        raise SafeError("交換#14の要求長が12件でない")
    req = [need(e.value) for e in req_run.events]
    cmds = commands(rows, req_run.lo, response_run.lo)
    reads = [c for c in cmds if c.opcode == 0x06]
    if len(reads) != 5 or any(len(r.params) != 8 or len(r.inputs) < 7 for r in reads):
        raise SafeError("交換#14のREAD DATA 5回を完全に抽出できない")
    expected = [need(e.value) for e in rows
                if e.cpu == "main" and e.kind == "IN" and e.port == "00FD"]
    if len(expected) != 5635:
        raise SafeError("公式main IN $FDが5635件でない")
    return req, expected[:3], expected[3:], reads


def load_extract(path: Path) -> tuple[list[int], list[int], list[int], list[Command]]:
    rows, masked = m2s.parse_iolog(path)
    if sum(masked.values()):
        raise SafeError("伏せ字ログでは位置対応を測定できない")
    return extract(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("iolog", type=Path)
    ap.add_argument("--disk-compare", type=Path,
                    help="内容差し替え媒体の生ログ（値は出力しない）")
    ap.add_argument("--config-compare", action="append", type=Path, default=[],
                    help="構成変更条件の生ログ（複数指定可、値は出力しない）")
    args = ap.parse_args()
    try:
        rows, masked = m2s.parse_iolog(args.iolog)
        if sum(masked.values()):
            raise SafeError("伏せ字ログでは位置対応を測定できない")
        tx = m2s.classify_transactions(rows)
        runs = boot.group_runs(tx)
        _, bulk_run = boot.split_boot_and_bulk(runs)
        pairs = boot.pair_rounds(runs)
        if len(pairs) < 15 or bulk_run is None:
            raise SafeError("交換#14または公式バルク区間を特定できない")
        req_run, response_run = pairs[14]
        if len(req_run.events) != 12:
            raise SafeError("交換#14の要求長が12件でない")
        req = [need(e.value) for e in req_run.events]
        cmds = commands(rows, req_run.lo, response_run.lo)
        read_indexes = [i for i, c in enumerate(cmds) if c.opcode == 0x06]
        reads = [cmds[i] for i in read_indexes]
        if len(reads) != 5 or any(len(r.params) != 8 or len(r.inputs) < 7 for r in reads):
            raise SafeError("交換#14のREAD DATA 5回を完全に抽出できない")

        print("# 交換#14 READ DATA位置対応（値は非表示）")
        print("READパラメータ位置: 0=unit/head 1=C 2=H 3=R 4=N 5=EOT 6=GPL 7=DTL")
        print("一致ベクトルはREAD #1..#5の順（1=一致、0=不一致）")
        print("\n## 要求12位置との対応")
        for k, q in enumerate(req):
            src = [q] * 5
            cells = [f"p{p}:{vector(src, reads, p)}" for p in range(8)]
            print(f"req[{k}]: " + "  ".join(cells))

        print("\n## 各READ直前のFDC結果との対応")
        result_sources: dict[str, list[int]] = {}
        for ri, ci in enumerate(read_indexes):
            prev_read = latest_before(cmds, ci, 0x06)
            sis = latest_before(cmds, ci, 0x08)
            if sis is None or len(sis.inputs) < 2:
                raise SafeError("READ直前のSENSE INTERRUPT STATUS結果が不足")
            result_sources.setdefault("SIS.ST0", []).append(sis.inputs[-2])
            result_sources.setdefault("SIS.PCN", []).append(sis.inputs[-1])
            if prev_read is not None and len(prev_read.inputs) >= 7:
                tail = prev_read.inputs[-7:]
                for name, pos in (("prev.ST0", 0), ("prev.ST1", 1), ("prev.ST2", 2),
                                  ("prev.C", 3), ("prev.H", 4), ("prev.R", 5), ("prev.N", 6)):
                    result_sources.setdefault(name, []).append(tail[pos])
            elif ri == 0:
                # 交換#14より前の直近READも探索対象に含める。
                earlier = [c for c in commands(rows, 0, req_run.lo) if c.opcode == 0x06]
                if earlier and len(earlier[-1].inputs) >= 7:
                    tail = earlier[-1].inputs[-7:]
                    for name, pos in (("prev.ST0", 0), ("prev.ST1", 1), ("prev.ST2", 2),
                                      ("prev.C", 3), ("prev.H", 4), ("prev.R", 5), ("prev.N", 6)):
                        result_sources.setdefault(name, []).append(tail[pos])
        for name, src in result_sources.items():
            if len(src) != 5:
                raise SafeError("直前FDC結果の対応列を5回分構成できない")
            cells = [f"p{p}:{vector(src, reads, p)}" for p in range(8)]
            print(f"{name}: " + "  ".join(cells))

        print("\n## READ間の公開FDC進行規則")
        coords = [(r.params[1], r.params[2], r.params[3], r.params[5]) for r in reads]
        checks = {
            "次R=前R+1": lambda a, b: b[2] == ((a[2] + 1) & 0xFF),
            "次R=前EOT+1": lambda a, b: b[2] == ((a[3] + 1) & 0xFF),
            "次R=1": lambda a, b: b[2] == 1,
            "次C=前C": lambda a, b: b[0] == a[0],
            "次C=前C+1": lambda a, b: b[0] == ((a[0] + 1) & 0xFF),
            "次H=前H": lambda a, b: b[1] == a[1],
            "次H=前H反転": lambda a, b: b[1] == (a[1] ^ 1),
            "前R=前EOT": lambda a, b: a[2] == a[3],
        }
        for name, fn in checks.items():
            bits = ["1" if fn(a, b) else "0" for a, b in zip(coords, coords[1:])]
            print(f"{name}: {''.join(bits)} ({bits.count('1')}/4)")
        lengths = [len(r.inputs) - 7 for r in reads]
        print("データ部長: " + ",".join(str(n) for n in lengths) + "件")

        print("\n## 公式main IN $FD 5635件との位置対応")
        expected = [need(e.value) for e in rows
                    if e.cpu == "main" and e.kind == "IN" and e.port == "00FD"]
        if len(expected) != 5635:
            raise SafeError("公式main IN $FDが5635件でない")
        head, body = expected[:3], expected[3:]
        data = [r.inputs[:-7] for r in reads]
        for i, d in enumerate(data, start=1):
            print(f"READ#{i}先頭 vs 公式先頭3件: {prefix_len(head, d)}/3")
            print(f"READ#{i}先頭 vs 公式定常5632件: {prefix_len(body, d)}件")
            needle = body[:16]
            offsets = [j for j in range(max(0, len(d) - len(needle) + 1))
                       if d[j:j + len(needle)] == needle]
            if offsets:
                print(f"READ#{i}内の公式定常先頭16件一致: {len(offsets)}箇所、先頭offset={offsets[0]}")
            else:
                print(f"READ#{i}内の公式定常先頭16件一致: 0箇所")
        concatenated = [v for d in data for v in d]
        print(f"READデータ単純連結 vs 公式先頭3件: {prefix_len(head, concatenated)}/3")
        print(f"READデータ単純連結 vs 公式定常5632件: {prefix_len(body, concatenated)}件")

        for i, value in enumerate(head):
            req_hits = [k for k, v in enumerate(req) if v == value]
            param_hits = [(ri + 1, p) for ri, r in enumerate(reads)
                          for p, v in enumerate(r.params) if v == value]
            result_hits = [(ri + 1, p) for ri, r in enumerate(reads)
                           for p, v in enumerate(r.inputs[-7:]) if v == value]
            print(f"公式先頭[{i}]一致元: req={req_hits} READparam={param_hits} READresult={result_hits}")

        parallel = [need(e.value) for e in rows if e.cpu == "main" and e.kind == "IN"
                    and e.port == "00FC" and e.pc == "C269"]
        print("\n## 並行main IN $FC定常5632件との位置対応")
        print(f"並行定常件数: {len(parallel)}")
        for i, d in enumerate(data, start=1):
            print(f"READ#{i}先頭 vs 並行定常: {prefix_len(parallel, d)}件")
        print(f"READデータ単純連結 vs 並行定常: {prefix_len(parallel, concatenated)}件")
        payload = [v for d in data for v in d[256:]]
        even = payload[0::2]
        odd = payload[1::2]
        print("\n## 各READ先頭1セクタ除外＋偶奇分離候補")
        print(f"候補総長: {len(payload)}件 / 偶数位置: {len(even)}件 / 奇数位置: {len(odd)}件")
        print(f"main IN $FD定常 vs 偶数位置: {prefix_len(body, even)}件")
        print(f"main IN $FD定常 vs 奇数位置: {prefix_len(body, odd)}件")
        print(f"main IN $FC定常 vs 偶数位置: {prefix_len(parallel, even)}件")
        print(f"main IN $FC定常 vs 奇数位置: {prefix_len(parallel, odd)}件")
        half = len(payload) // 2
        print(f"main IN $FD定常 vs 前半: {prefix_len(body, payload[:half])}件")
        print(f"main IN $FD定常 vs 後半: {prefix_len(body, payload[half:])}件")
        print(f"main IN $FC定常 vs 前半: {prefix_len(parallel, payload[:half])}件")
        print(f"main IN $FC定常 vs 後半: {prefix_len(parallel, payload[half:])}件")
        semantic = {
            "READ回数": len(reads),
            "除外セクタ数": len(reads),
            "転送組数": len(body) // 256,
            "両ポート転送セクタ数": len(payload) // 256,
            "転送件数下位": len(body) & 0xFF,
            "転送件数上位": (len(body) >> 8) & 0xFF,
            "全受信件数下位": len(expected) & 0xFF,
            "全受信件数上位": (len(expected) >> 8) & 0xFF,
            "両ポート総件数下位": len(payload) & 0xFF,
            "両ポート総件数上位": (len(payload) >> 8) & 0xFF,
            "セクタ長下位": 256 & 0xFF,
            "セクタ長上位": (256 >> 8) & 0xFF,
            "READデータ総セクタ数": sum(len(d) for d in data) // 256,
            "入口phase[0]": 0x81,
            "入口phase[1]": 0x08,
            "入口phase[2]": 0x0A,
            "入口phase[3]": 0x0C,
            "入口phase[4]": 0x0E,
            "定常送信phase": 0x09,
            "固定N": 0x01,
            "固定GPL": 0x2A,
            "固定DTL": 0xFF,
        }
        all_data = [v for d in data for v in d]
        all_params = [v for r in reads for v in r.params]
        all_results = [v for r in reads for v in r.inputs[-7:]]
        semantic.update({
            "要求加算和": fold_sum(req), "要求XOR": fold_xor(req),
            "READパラメータ加算和": fold_sum(all_params),
            "READパラメータXOR": fold_xor(all_params),
            "FDC結果加算和": fold_sum(all_results),
            "FDC結果XOR": fold_xor(all_results),
            "READデータ加算和": fold_sum(all_data),
            "READデータXOR": fold_xor(all_data),
            "転送組数-1": len(body) // 256 - 1,
            "転送組数+1": len(body) // 256 + 1,
            "転送総セクタ数": len(body) // 256,
            "残余バイト数": len(body) % 256,
            "READ総セクタ数-転送組数": len(all_data) // 256 - len(body) // 256,
            "READ総セクタ数-両ポート転送セクタ数": len(all_data) // 256 - len(payload) // 256,
            "除外後データ加算和": fold_sum(payload),
            "除外後データXOR": fold_xor(payload),
            "定常出力加算和": fold_sum(body),
            "定常出力XOR": fold_xor(body),
        })
        for ri, d in enumerate(data, 1):
            semantic[f"READ#{ri}セクタ数"] = len(d) // 256
            semantic[f"READ#{ri}加算和"] = fold_sum(d)
            semantic[f"READ#{ri}XOR"] = fold_xor(d)
            for si in range(0, len(d), 256):
                sec = d[si:si + 256]
                semantic[f"READ#{ri} sector{si // 256 + 1}加算和"] = fold_sum(sec)
                semantic[f"READ#{ri} sector{si // 256 + 1}XOR"] = fold_xor(sec)
        print("\n## 公式先頭3件と構造量候補")
        print(f"先頭3位置の同値グループ数: {len(set(head))}")
        for i, value in enumerate(head):
            labels = [label for label, candidate in semantic.items() if value == candidate]
            print(f"公式先頭位置{i + 1}: 一致候補数={len(labels)} 同値候補群数={len(set(semantic[x] for x in labels))} 候補={labels}")

        print("\n## ヘッダ後の256件境界によるREADデータ位置対応")
        source_sectors = [d[o:o + 256] for d in data for o in range(0, len(d), 256)]
        body_sectors = [body[o:o + 256] for o in range(0, len(body), 256)]
        hit_counts = [sum(s == t for s in source_sectors) for t in body_sectors]
        unique = sum(n == 1 for n in hit_counts)
        any_hit = sum(n > 0 for n in hit_counts)
        byte_hits = 0
        for target, n in zip(body_sectors, hit_counts):
            if n:
                source = next(s for s in source_sectors if s == target)
                byte_hits += sum(a == b for a, b in zip(target, source))
        print(f"出力セクタ一致: {any_hit}/{len(body_sectors)}、一意対応: {unique}/{len(body_sectors)}")
        print(f"一意/同値候補を含む位置一致件数: {byte_hits}/{len(body)}")
        print(f"出力セクタ同値グループ数: {len({tuple(x) for x in body_sectors})} / READ側: {len({tuple(x) for x in source_sectors})}")

        def compare(label: str, other_path: Path) -> None:
            try:
                _, other_head, other_body, other_reads = load_extract(other_path)
            except SafeError as exc:
                print(f"{label}: 比較不能（{exc}）")
                return
            same = [a == b for a, b in zip(head, other_head)]
            changed_fdc = sum(a != b for a, b in zip(all_data,
                [v for r in other_reads for v in r.inputs[:-7]]))
            print(f"{label}: 位置1={'同一' if same[0] else '相違'} 位置2={'同一' if same[1] else '相違'} 位置3={'同一' if same[2] else '相違'}、先頭一致={sum(same)}/3、同値グループ数={len(set(other_head))}、FDCデータ相違={changed_fdc}件、定常位置一致={sum(a == b for a, b in zip(body, other_body))}/{len(body)}")

        if args.disk_compare:
            print("\n## 説D 媒体差し替え連動")
            compare("媒体差し替え", args.disk_compare)
        if args.config_compare:
            print("\n## 説C 構成連動")
            for i, path in enumerate(args.config_compare, 1):
                compare(f"構成条件{i}", path)
        return 0
    except (SafeError, OSError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
