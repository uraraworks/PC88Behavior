#!/usr/bin/env python3
"""l4-t5（DELETE・TRON/TROFF）・l4-t6（INPUT$）・l4-t7（AUTO・RENUM）・l4-t8（ファンクションキー・ON KEY）の適合判定。

測定器具（tools/l4_t5_delete_measure.py・tools/l4_t6_inputdollar_measure.py）が出す
測定JSONから、仕様に関わる項目だけを射影して比べる。全体の一致は求めない
（機能キー表示行や誤り表示の文言など、この段で扱わない行まで比べると無関係な差で落ちるため）。

  project  --kind t5|t6 --measured M.json --out E.json   公式測定から期待値を作る
  check    --kind t5|t6 --measured M.json --expected E.json

射影するもの（本文は含まない。行署名と数値だけ）:
  t5: 各腕の同定ラベル、DELETE腕の行の生存と goto の誤り、
      TRON腕は「打鍵行の次からプロンプトの前まで」の行の文字数と行署名、プロンプト行の相対位置
  t6: 各腕の印の書込み列（番地・値）、直接腕の応答の行数・文字数
  t7: 操作の同定、候補番号ごとの印と応答、RUNの通り道、AUTOの番号行の署名
  t8: 応答の同定と印の書込み列（既定割り当て腕は長さを除く）
  t9: 応答の同定と印の書込み列（追補2の構成）
  t10: MOTOR の腕の印とポート30hの前後の値
  t10e: EDIT の腕の直後の画面の行署名（最下行を除く）・カーソル・印（追補1）
"""
import argparse
import json
import sys
from pathlib import Path


def project_t5(data):
    out = {}
    for name, rec in sorted(data['records'].items()):
        if not rec.get('gate'):
            raise ValueError(f'{name}: 関門を通っていない')
        run = rec['runs'][0]
        item = {'identification': rec.get('identification')}
        mem = run['memory']
        if mem.get('survival') is not None:
            item['survival'] = mem['survival']
            item['goto_err'] = mem['goto_err']
        if name.startswith('trace-'):
            start, prompt = run['start'], run['prompt']
            item['prompt_offset'] = prompt - start
            item['trace_rows'] = [[r['row'] - start, r['char_count'], r['sha256']]
                                  for r in run['rows'] if start < r['row'] < prompt]
        out[name] = item
    return out


def project_t6(data):
    out = {}
    for name, rec in sorted(data['records'].items()):
        if not rec.get('gate', True):
            raise ValueError(f'{name}: 関門を通っていない')
        run = rec['runs'][0]
        item = {'writes': run['memory']['writes']}
        if 'response' in run:
            item['response'] = [[r['line_count'], r['char_count']] for r in run['response']]
        out[name] = item
    return out


def project_t7(data):
    out = {}
    for name, rec in sorted(data['records'].items()):
        if not rec.get('gate'):
            raise ValueError(f'{name}: 関門を通っていない')
        res = rec.get('result') or {}
        item = {'operation': res.get('operation')}
        if 'probes' in res:
            item['probes'] = {k: [v['marks'], v['response']] for k, v in res['probes'].items()}
        for key in ('run_order_equal', 'after_run'):
            if key in res:
                item[key] = res[key]
        if 'auto_screen' in res:
            # 行7＝表示した行番号の行。番号の後ろの空白は署名の前に落ちる。
            item['auto_number_row'] = res['auto_screen']['7']
        out[name] = item
    return out


def project_t8(data):
    out = {}
    for name, rec in sorted(data['records'].items()):
        if not rec.get('gate'):
            raise ValueError(f'{name}: 関門を通っていない')
        run = rec['runs'][0]
        writes = run['writes']
        if name == 'default':
            # 既定の割り当ては自作の値を使う（l4-program 5.7.6）。長さと値は比べない。
            writes = [w for w in writes if w[0] != 0xe010]
        out[name] = {'response': rec.get('response'), 'writes': writes}
    return out


def project_t9(data):
    out = {}
    for name, rec in sorted(data['records'].items()):
        if not rec.get('gate'):
            raise ValueError(f'{name}: 関門を通っていない')
        run = rec['runs'][0]
        out[name] = {'responses': rec.get('responses'), 'writes': run['writes']}
    return out


def project_t10(data):
    # MOTOR の腕だけ（EDIT は追補で測り直す）。ポート30h(48)の最後の値と誤りの同定。
    out = {}
    for name, rec in sorted(data['records'].items()):
        if not name.startswith(('motor-', 'ref-')) or not rec.get('gate'):
            continue
        run = rec['runs'][0]
        item = {'writes': run['writes']}
        if 'out_last_before_after' in run:
            before, after = run['out_last_before_after']
            item['port30'] = [before.get('48'), after.get('48')]
        out[name] = item
    return out


def project_t10e(data):
    # EDIT（l4-t10 追補1）。EDIT の直後の画面の非空行（最下行を除く）の行署名、カーソル、印。
    out = {}
    for name, rec in sorted(data['records'].items()):
        if not name.startswith('edit-') or not rec.get('gate'):
            continue
        run = rec['runs'][0]
        rows = run['screen'].get('operationa', {})
        out[name] = {
            'rows': sorted([int(r), v[0], v[1]] for r, v in rows.items() if v[0] and int(r) != 19),
            'cursor': run.get('cursor_crtc'),
            'writes': run['writes'],
        }
    return out


PROJECT = {'t5': project_t5, 't6': project_t6, 't7': project_t7, 't8': project_t8, 't9': project_t9, 't10': project_t10, 't10e': project_t10e}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('project')
    p.add_argument('--kind', choices=PROJECT, required=True)
    p.add_argument('--measured', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('check')
    c.add_argument('--kind', choices=PROJECT, required=True)
    c.add_argument('--measured', type=Path, required=True)
    c.add_argument('--expected', type=Path, required=True)
    a = ap.parse_args()
    got = PROJECT[a.kind](json.loads(a.measured.read_text()))
    if a.cmd == 'project':
        a.out.write_text(json.dumps(got, ensure_ascii=False, sort_keys=True, indent=1) + '\n')
        return 0
    want = json.loads(a.expected.read_text())
    # l4-program.md 11.3 の自作の判断により通常 SAVE は ASCII。公式との差異。
    if a.kind == 't9':
        want.pop('merge-binary')
    bad = 0
    for name in sorted(want):
        if name not in got:
            print(f'NG {name}: 測定に無い'); bad += 1; continue
        for key in sorted(want[name]):
            if got[name].get(key) != want[name][key]:
                print(f'NG {name}: {key}'); bad += 1
    print(f'{a.kind}: {len(want) - len({n for n in want if n not in got})}腕中 不一致{bad}件')
    return 1 if bad else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as exc:
        print('NG 器具:', type(exc).__name__, '（本文非出力）')
        raise SystemExit(1)
