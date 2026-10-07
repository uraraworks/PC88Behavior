#!/usr/bin/env python3
"""tools/runall_cache.py — run_all_selftests.sh の入力キャッシュと静的検査。

目的: 「入力がバイト単位で前回合格時と同じ」ときだけ selftest の再実行を
飛ばす。推測で飛ばさない（過去に「関係なさそう」で RAM 配置変更の退行5本を
見逃した）。取りこぼしの疑いがあれば必ず実行側（安全側）へ倒す。

サブコマンド:
  gfp                   全スクリプト共通の指紋（tools/ tests/ vendor 環境 …）を表示
  analyze SCRIPT        静的解析の結果(JSON)を表示（デバッグ・自己検査用）
  plan SCRIPT --plan-file F   実行方針を1行で出す: cached|both|utf8 と理由。
                        F に記録用の状態を書く
  record --plan-file F --status pass|ng|skip --mode both|utf8 --logs L...
                        結果を記録（pass のときだけキャッシュに残す）
  lint                  tools/**/*.sh の「$var 直後の非ASCII文字」を静的検出
  clear                 キャッシュを捨てる

キャッシュは PC88_RUNALL_CACHE_DIR（既定: <repo>/../tmp/runall-cache）。
キャッシュに書くのはファイルのハッシュと相対パスだけ。private/ 配下は
パスもハッシュ化し（メモの鍵）、名前を一切書かない。

指紋の中身（pass を再利用してよい条件 = 全部一致）:
  G  tools/ と tests/ の全ファイル（追跡の有無を問わず＝ビルド済みの
     q88measure 等も含む。__pycache__ 除く）、../vendor 全体（コア・ビルド
     済みバイナリ含む）、private/ の内容、PC88_* 環境変数（PC88_REF_* が
     指すファイル・ディレクトリは内容ハッシュ）、python/bash/OS の版
  E  スクリプトの閉包に PC88_SELFTEST_EXCLUDE が現れる場合だけ、その値と
     それが指すファイルの内容（分割実行でキャッシュを積み上げるため、他の
     スクリプトには入れない）
  D  リポジトリ側の入力（src/ docs/ measurements/ …）。
     recorded: 前回の実行で実際に読んだ（open/stat/listdir）ファイル集合の
               内容。python フックの記録（tools/runall_hook）による。
     full    : 記録が信用できない場合の安全側。src/ 全体＋閉包に名前が現れる
               トップレベルの dir/file 全体。
     rw      : git の ls-files/show 等に依存する場合。tree と作業ツリー全体。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
VERSION = 1


def die(msg):
    sys.stderr.write("runall_cache: %s\n" % msg)
    sys.exit(2)


def cache_dir():
    d = os.environ.get("PC88_RUNALL_CACHE_DIR")
    if not d:
        d = os.path.join(os.path.dirname(REPO), "tmp", "runall-cache")
    return d


def sha(b):
    return hashlib.sha256(b).hexdigest()


def hstr(s):
    return sha(s.encode("utf-8", "surrogateescape"))


# ---------------------------------------------------------------- ファイルハッシュ
class Memo:
    """(パスのハッシュ, size, mtime_ns, ino) -> 内容ハッシュ。パスは残さない。"""

    def __init__(self):
        self.path = os.path.join(cache_dir(), "memo.json")
        self.d = {}
        self.dirty = False
        try:
            with open(self.path) as f:
                self.d = json.load(f)
        except Exception:
            self.d = {}

    def file_hash(self, p):
        try:
            st = os.stat(p)
        except OSError:
            return "ABSENT"
        key = hstr(p) + ":%d:%d:%d" % (st.st_size, st.st_mtime_ns, st.st_ino)
        h = self.d.get(key)
        if h is None:
            hh = hashlib.sha256()
            try:
                with open(p, "rb") as f:
                    for blk in iter(lambda: f.read(1 << 20), b""):
                        hh.update(blk)
            except OSError:
                return "UNREADABLE"
            h = hh.hexdigest()
            self.d[key] = h
            self.dirty = True
        return h

    def save(self):
        if not self.dirty:
            return
        try:
            os.makedirs(cache_dir(), exist_ok=True)
            tmp = self.path + ".%d" % os.getpid()
            with open(tmp, "w") as f:
                json.dump(self.d, f)
            os.replace(tmp, self.path)
        except OSError:
            pass


SKIP_NAMES = {"__pycache__", ".DS_Store", ".git"}


def walk_hash(memo, root, rel_prefix=""):
    """ディレクトリ(またはファイル)の内容ハッシュ。相対パスと内容を畳み込む。"""
    h = hashlib.sha256()
    if os.path.isfile(root) or os.path.islink(root) and not os.path.isdir(root):
        h.update(b"file:" + memo.file_hash(root).encode())
        return h.hexdigest()
    if not os.path.isdir(root):
        return "ABSENT"
    for dp, dns, fns in os.walk(root, followlinks=False):
        dns[:] = sorted(d for d in dns if d not in SKIP_NAMES)
        for fn in sorted(fns):
            if fn in SKIP_NAMES or fn.endswith(".pyc"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                if os.path.isfile(p):
                    t = "L:" + memo.file_hash(p)
                else:
                    t = "L:" + os.readlink(p)
            else:
                t = memo.file_hash(p)
            h.update(rel.encode("utf-8", "surrogateescape") + b"\0" + t.encode() + b"\n")
        for d in dns:
            p = os.path.join(dp, d)
            if os.path.islink(p):
                h.update(os.path.relpath(p, root).encode("utf-8", "surrogateescape")
                         + b"\0LD:" + os.readlink(p).encode("utf-8", "surrogateescape") + b"\n")
    return h.hexdigest()


def tool_versions():
    out = [sys.version, sys.executable]
    for cmd in (["bash", "--version"], ["uname", "-sm"], ["cc", "--version"]):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=20)
            out.append((r.stdout.decode("utf-8", "replace").splitlines() or [""])[0])
        except Exception:
            out.append("none")
    return "\n".join(out)


def env_component(memo):
    parts = []
    for k in sorted(os.environ):
        if not k.startswith("PC88_") or k.startswith("PC88_RUNALL_"):
            continue
        if k == "PC88_SELFTEST_EXCLUDE":
            continue  # スクリプト別(E)に入れる
        v = os.environ[k]
        item = k + "=" + hstr(v)
        if k.startswith("PC88_REF_") and v:
            item += ":" + walk_hash(memo, v)
        parts.append(item)
    return hstr("\n".join(parts))


def global_fp(memo):
    comp = {}
    comp["tools"] = walk_hash(memo, os.path.join(REPO, "tools"))
    comp["tests"] = walk_hash(memo, os.path.join(REPO, "tests"))
    comp["vendor"] = walk_hash(memo, os.path.join(os.path.dirname(REPO), "vendor"))
    comp["private"] = walk_hash(memo, os.path.join(REPO, "private"))
    comp["env"] = env_component(memo)
    comp["tool"] = hstr(tool_versions())
    comp["ver"] = str(VERSION)
    return hstr(json.dumps(comp, sort_keys=True)), comp


# ---------------------------------------------------------------- 静的解析
TOP_SKIP = {"tools", "tests", ".git", "private", "__pycache__", ".DS_Store", "tmp", "build"}


def top_level_names():
    try:
        return sorted(n for n in os.listdir(REPO) if n not in TOP_SKIP)
    except OSError:
        return []


_index = None


def file_index():
    """basename -> [相対パス]（tools/ src/ tests/ 配下の .sh .py）"""
    global _index
    if _index is not None:
        return _index
    idx = {}
    for top in ("tools", "src", "tests"):
        for dp, dns, fns in os.walk(os.path.join(REPO, top)):
            dns[:] = [d for d in dns if d not in SKIP_NAMES]
            for fn in fns:
                if fn.endswith((".sh", ".py")):
                    idx.setdefault(fn, []).append(
                        os.path.relpath(os.path.join(dp, fn), REPO))
    _index = idx
    return idx


NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*\.(?:sh|py)\b")
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)


_text_cache = {}
_names_cache = {}
_lines_cache = {}


def read_text(rel_or_abs):
    if rel_or_abs in _text_cache:
        return _text_cache[rel_or_abs]
    t = _read_text(rel_or_abs)
    _text_cache[rel_or_abs] = t
    return t


def _read_text(rel_or_abs):
    p = rel_or_abs if os.path.isabs(rel_or_abs) else os.path.join(REPO, rel_or_abs)
    try:
        with open(p, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


MSG_RE = re.compile(
    r"""(?<![\w-])(?:echo|printf|fail|pass|ng|ok|die|skip|warn|note|info|log|say|usage)"""
    r"""(?![\w-])\s+(?:-\w+\s+)?(?:"(?:[^"\\]|\\.)*"|'[^']*')""")


def strip_messages(s):
    return MSG_RE.sub(" ", s)


def referenced_names(rel, text):
    """そのファイルが実行・import する先の名前候補（コメント・docstring を除く）。"""
    names = set()
    if rel.endswith("run_all_selftests.sh"):
        # 登録表（全 selftest の名前の列挙）は「呼ぶ」関係ではない
        text = re.sub(r"(?ms)^SCRIPTS_EXPECTED=\(.*?^\)", "", text)
    if rel.endswith(".py"):
        import ast
        try:
            tree = ast.parse(text)
        except Exception:
            tree = None
        if tree is not None:
            doc_ids = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)):
                    b = getattr(node, "body", None)
                    if b and isinstance(b[0], ast.Expr) and isinstance(
                            getattr(b[0], "value", None), ast.Constant):
                        doc_ids.add(id(b[0].value))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and id(node) not in doc_ids:
                    if re.search(r"\s", node.value):
                        continue  # 空白を含む文字列は文言（エラーメッセージ等）
                    for m in NAME_RE.finditer(node.value):
                        names.add(m.group(0))
                elif isinstance(node, ast.Import):
                    for al in node.names:
                        names.add(al.name.split(".")[0] + ".py")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.add(node.module.split(".")[0] + ".py")
                    for al in node.names:
                        names.add(al.name + ".py")
            return names
    body = strip_messages("\n".join(
        l for l in text.split("\n") if not l.lstrip().startswith("#")))
    for m in NAME_RE.finditer(body):
        names.add(m.group(0))
    for m in IMPORT_RE.finditer(body):
        names.add(m.group(1) + ".py")
    return names


def closure(script):
    """script から名前で辿れる .sh/.py の集合（基本名の一致による上位集合）。"""
    idx = file_index()
    rel = os.path.relpath(os.path.abspath(script), REPO) if os.path.isabs(script) \
        else script
    seen = []
    q = [rel]
    seenset = {rel}
    while q:
        r = q.pop()
        seen.append(r)
        if r not in _names_cache:
            _names_cache[r] = referenced_names(r, read_text(r))
        for n in _names_cache[r]:
            for c in idx.get(n, []):
                if c not in seenset:
                    seenset.add(c)
                    q.append(c)
    return sorted(seen)


HEREDOC_RE = re.compile(r"<<(?!<)(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def shell_logical_lines(text):
    """(行番号, 論理行) を返す。コメント行・ヒアドキュメント本体は除く。"""
    out = []
    lines = text.split("\n")
    i = 0
    n = len(lines)
    pending_delims = []
    buf = ""
    start = 0
    while i < n:
        ln = lines[i]
        if pending_delims:
            d, dash = pending_delims[0]
            chk = ln.lstrip("\t") if dash else ln
            if chk == d:
                pending_delims.pop(0)
            i += 1
            continue
        if not buf:
            start = i + 1
            if ln.lstrip().startswith("#"):
                i += 1
                continue
        if ln.endswith("\\"):
            buf += ln[:-1] + " "
            i += 1
            continue
        full = buf + ln
        buf = ""
        for m in HEREDOC_RE.finditer(full):
            pending_delims.append((m.group(3), m.group(1) == "-"))
        out.append((start, full))
        i += 1
    return out


LIT_PATH_RE = re.compile(
    r"(?<![\w.-])(?:\$\{?\w*REPO\w*\}?/|\./)?((?:src|docs|measurements)/[A-Za-z0-9_./-]*[A-Za-z0-9_])")
GIT_IMMUT_SEG_RE = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?(?:archive|clone|checkout|worktree)\b")
SEG_SPLIT_RE = re.compile(r"\|\||&&|\||;|\{|\}|\$\(|\(|\)|`")
VENDOR_SRC_RE = re.compile(r"\$\{?[A-Za-z_]*(?:VENDOR|SRC)[A-Za-z_]*\}?/src\b")
ASSIGN_RE = re.compile(
    r"^\s*(?:export\s+|local\s+|readonly\s+|declare\s+(?:-\S+\s+)?)?([A-Za-z_]\w*)=(.*)$")
FOR_RE = re.compile(r"^\s*for\s+([A-Za-z_]\w*)\s+in\s+(.*)$")
UNSAFE_CMD_RE = re.compile(
    r"(?<![\w-])(cat|grep|egrep|fgrep|rg|sed|awk|gawk|diff|cmp|shasum|sha256sum|"
    r"sha1sum|md5|md5sum|wc|head|tail|cp|mv|tar|xxd|od|hexdump|find|ls|sort|uniq|"
    r"source|rsync|ln|dd|tee|cut|tr|stat|touch|zip|unzip|git|make|cc|gcc|clang|"
    r"xargs|readlink|realpath|diff3|patch|file|strings|nl|paste|join|comm|split|"
    r"csplit|iconv|nkf|base64|openssl|jq|perl|ruby|node)(?![\w-])")
INREDIR_RE = re.compile(r"(?<![<\d])<(?![<(])")
PY_SUBPROC_RE = re.compile(
    r"subprocess|os\.system|os\.popen|os\.exec|os\.spawn|Popen|shell\s*=\s*True")
PY_UNSAFE_LIT_RE = re.compile(
    r"""["'](cat|grep|egrep|fgrep|rg|sed|awk|diff|cmp|shasum|sha256sum|md5|md5sum|"""
    r"""wc|head|tail|cp|mv|tar|xxd|od|hexdump|find|ls|sort|source|rsync|ln|dd|tee|"""
    r"""cut|tr|git|make|xargs|patch|strings|iconv|perl)["']""")
GIT_SH_RE = re.compile(
    r"(?:^|[\s;&|(`$])git\s+(?:-C\s+\S+\s+)?([a-z][a-z-]*)")
GIT_PY_RE = re.compile(
    r"""["']git["']\s*(?:,\s*(?:["']-C["']\s*,\s*[^,\]]+,\s*)?["']([a-z][a-z-]*)["'])?""")
IMMUTABLE_GIT = {"archive", "clone", "checkout", "worktree", "init", "config",
                 "rev-parse", "cat-file", "--version", "version"}
PYFLAG_RE = re.compile(r"python3?\s+(?:-\w+\s+)*-[A-Za-z]*[ISE][A-Za-z]*(?:\s|$)")
PYFLAG2_RE = re.compile(r"""["']-[A-Za-z]*[ISE][A-Za-z]*["']""")
TMP_INPUT_RE = re.compile(r"\.\./tmp/|PC88/tmp/")


def analyze(script):
    rel = os.path.relpath(os.path.abspath(script), REPO) \
        if os.path.isabs(script) else script
    clo = [f for f in closure(rel)
           if f not in ("tools/runall_cache.py", "tools/runall_hook/sitecustomize.py")]
    reasons = []
    static_paths = set()
    rw = False
    rw_reasons = []
    uncacheable = []
    sh_files = [f for f in clo if f.endswith(".sh")]
    py_files = [f for f in clo if f.endswith(".py")]
    texts = {f: read_text(f) for f in clo}
    alltext = "\n".join(texts.values())

    # 閉包に現れるリポジトリ側の dir/file 名（full の範囲）
    dep_names = ["src"]
    for name in top_level_names():
        if name == "src":
            continue
        pat = r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])"
        if re.search(pat, alltext):
            dep_names.append(name)
    dep_names = sorted(set(dep_names))

    uses_python = bool(py_files) or bool(re.search(r"\bpython3?\b", alltext))

    # 1) フックが効かない形
    for f in clo:
        t = texts[f]
        body = "\n".join(l for l in t.split("\n") if not l.lstrip().startswith("#"))
        if "PYTHONPATH" in body:
            reasons.append("%s: PYTHONPATH を触る（フックが外れうる）" % f)
        if "PC88_RUNALL" in body and not f.endswith(
                ("run_all_selftests.sh", "run_all_selftests_selftest.sh",
                 "runall_cache.py", "sitecustomize.py")):
            reasons.append("%s: 記録フックの環境変数を触る" % f)
        if PYFLAG_RE.search(body) or PYFLAG2_RE.search(body):
            reasons.append("%s: python の -I/-S/-E（フックが外れる）" % f)
        if re.search(r"\benv\s+-i\b|\benv\s+-u\b", body):
            reasons.append("%s: env -i（フックが外れる）" % f)
        if f.endswith(".py") and re.search(r"\benv\s*=", body) \
                and PY_SUBPROC_RE.search(body) and "os.environ" not in body:
            reasons.append("%s: subprocess に env= を渡す（フックが外れる）" % f)
        if TMP_INPUT_RE.search(body):
            uncacheable.append("%s: ../tmp の資料を入力にしている" % f)

    # 2) python 以外の経路でリポジトリ側を読む
    dep_tok = "|".join(re.escape(n) for n in dep_names)
    TOK = re.compile(r"(?<![\w.${-])(?:" + dep_tok + r")(?![\w-])")
    for f in sh_files:
        if f not in _lines_cache:
            _lines_cache[f] = [(no, VENDOR_SRC_RE.sub("VSRC", strip_messages(ln)))
                               for no, ln in shell_logical_lines(texts[f])]
    # 変数名はファイルごと（別ファイルの同名変数に汚染を広げない）。
    # source/. で読み込む相手がいる場合は相手のファイルの汚染も引き継ぐ。
    file_taint = {}
    parsed_by = {}
    for f in sh_files:
        parsed = []
        for no, ln in _lines_cache[f]:
            m = ASSIGN_RE.match(ln)
            kind = "A"
            if not m:
                m = FOR_RE.match(ln)
                kind = "F"
            parsed.append((f, no, ln, kind if m else None,
                           m.group(1) if m else None, m.group(2) if m else None))
        parsed_by[f] = parsed

    def taint_of(plist, tainted):
        def var_re():
            if not tainted:
                return None
            return re.compile(r"\$\{?(?:" + "|".join(sorted(map(re.escape, tainted)))
                              + r")(?![\w])")
        changed = True
        while changed:
            changed = False
            vre = var_re()
            for f, no, ln, kind, tgt, rhs in plist:
                if tgt and tgt not in tainted:
                    if TOK.search(rhs) or (vre and vre.search(rhs)):
                        tainted.add(tgt)
                        changed = True
        return var_re()

    def sourced_by(f):
        res = []
        for m in re.finditer(r"(?m)^\s*(?:source|\.)\s+(\S.*)$", texts[f]):
            for n in NAME_RE.finditer(m.group(1)):
                for c in file_index().get(n.group(0), []):
                    if c in parsed_by and c != f:
                        res.append(c)
        return res

    for f in sh_files:
        tainted = set()
        plist = list(parsed_by[f])
        for g in sourced_by(f):
            plist += parsed_by[g]
        vre = taint_of(plist, tainted)
        for ff, no, ln, kind, tgt, rhs in parsed_by[f]:
            hit = bool(TOK.search(ln)) or bool(vre and vre.search(ln))
            if not hit:
                continue
            if kind and not re.search(r"\$\(", ln):
                continue
            for seg in SEG_SPLIT_RE.split(ln):
                seg_hit = bool(TOK.search(seg)) or bool(vre and vre.search(seg))
                if not seg_hit:
                    continue
                if GIT_IMMUT_SEG_RE.search(seg):
                    continue
                if not (UNSAFE_CMD_RE.search(seg) or INREDIR_RE.search(seg)):
                    continue
                # リテラルのファイルパスだけを読む行は、そのファイルを静的依存に足す
                lits = [m for m in LIT_PATH_RE.finditer(seg)]
                rest = LIT_PATH_RE.sub(" ", seg)
                ok_lits = bool(lits) and not TOK.search(rest) \
                    and not (vre and vre.search(seg)) \
                    and all(not os.path.isdir(os.path.join(REPO, m.group(1)))
                            and not seg[m.end():m.end() + 1] in ("*", "?", "[", "{")
                            for m in lits)
                if ok_lits:
                    for m in lits:
                        static_paths.add(m.group(1))
                else:
                    reasons.append("%s:%d: シェルが直接読む疑い（python 以外）" % (f, no))
                    break
    for f in py_files:
        body = texts[f]
        if PY_SUBPROC_RE.search(body) and PY_UNSAFE_LIT_RE.search(body):
            reasons.append("%s: python から読み取り系の外部コマンドを呼ぶ" % f)
        if "os.system" in body or "shell=True" in body:
            reasons.append("%s: os.system/shell=True" % f)

    # 3) git
    for f in clo:
        body = "\n".join(l for l in texts[f].split("\n")
                         if not l.lstrip().startswith("#"))
        subs = set()
        if f.endswith(".sh"):
            for no, ln in shell_logical_lines(texts[f]):
                for m in GIT_SH_RE.finditer(ln):
                    subs.add(m.group(1))
        for m in GIT_PY_RE.finditer(body):
            subs.add(m.group(1) or "?")
        for s in subs:
            if s not in IMMUTABLE_GIT:
                rw = True
                rw_reasons.append("%s: git %s" % (f, s))

    sh_text_for_fp = "".join(
        "\0%s\0%s" % (f, texts[f]) for f in sorted(sh_files))
    shell_fp = hstr(sh_text_for_fp)
    mentions_exclude = "PC88_SELFTEST_EXCLUDE" in alltext
    return {
        "script": rel,
        "closure": clo,
        "shell_fp": shell_fp,
        "dep_names": dep_names,
        "full_reasons": reasons,
        "static_paths": sorted(static_paths),
        "rw": rw,
        "rw_reasons": rw_reasons,
        "uncacheable": uncacheable,
        "uses_python": uses_python,
        "mentions_exclude": mentions_exclude,
    }


# ---------------------------------------------------------------- 依存の指紋
def git_out(*args):
    try:
        r = subprocess.run(["git", "-C", REPO] + list(args), capture_output=True,
                           timeout=120)
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return None


def rw_hash(memo):
    h = hashlib.sha256()
    tree = git_out("rev-parse", "HEAD^{tree}")
    h.update(tree if tree is not None else b"nogit")
    names = git_out("ls-files", "-co", "--exclude-standard", "-z")
    if names is None:
        h.update(walk_hash(memo, REPO).encode())
    else:
        for n in sorted(x for x in names.split(b"\0") if x):
            p = os.path.join(REPO, n.decode("utf-8", "surrogateescape"))
            h.update(n + b"\0" + memo.file_hash(p).encode() + b"\n")
    return h.hexdigest()


def dir_listing_hash(p):
    try:
        names = sorted(os.listdir(p))
    except OSError:
        return "ABSENT"
    parts = []
    for n in names:
        if n in SKIP_NAMES or n.endswith(".pyc"):
            continue
        q = os.path.join(p, n)
        parts.append(n + ("/" if os.path.isdir(q) else ""))
    return hstr("\n".join(parts))


def paths_hash(memo, paths):
    h = hashlib.sha256()
    for kind, rel in sorted(set(map(tuple, paths))):
        p = os.path.join(REPO, rel)
        if kind == "D" or os.path.isdir(p):
            t = "D:" + dir_listing_hash(p)
        else:
            t = "F:" + memo.file_hash(p)
        h.update((kind + "\0" + rel + "\0" + t + "\n").encode("utf-8", "surrogateescape"))
    return h.hexdigest()


def full_hash(memo, names):
    h = hashlib.sha256()
    for n in sorted(names):
        h.update(n.encode() + b"\0" + walk_hash(memo, os.path.join(REPO, n)).encode()
                 + b"\n")
    return h.hexdigest()


def exclude_component(memo, mentions):
    if not mentions:
        return "-"
    v = os.environ.get("PC88_SELFTEST_EXCLUDE", "")
    parts = ["set" if v else "unset", hstr(v)]
    for n in v.split():
        p = n if os.path.isabs(n) else os.path.join(REPO, n)
        parts.append(memo.file_hash(p))
    return hstr("\n".join(parts))


def entry_path(script):
    return os.path.join(cache_dir(), "e-" + hstr(script)[:32] + ".json")


def load_entry(script):
    try:
        with open(entry_path(script)) as f:
            e = json.load(f)
        if e.get("script") == script and e.get("ver") == VERSION:
            return e
    except Exception:
        pass
    return None


def head_commit():
    r = git_out("rev-parse", "--short", "HEAD")
    c = r.decode().strip() if r else "nogit"
    st = git_out("status", "--porcelain", "-uno")
    if st:
        c += "+dirty"
    return c


# ---------------------------------------------------------------- plan / record
def cmd_plan(a):
    memo = Memo()
    script = a.script
    info = analyze(script)
    gfp, comp = global_fp(memo)
    efp = exclude_component(memo, info["mentions_exclude"])
    ent = None if a.no_lookup else load_entry(script)
    plan = {"script": script, "gfp": gfp, "efp": efp, "shell_fp": info["shell_fp"],
            "info": info, "ver": VERSION}
    # 両ロケールが必要か: 前回「両ロケール合格」時とシェル側の文面が同じなら UTF-8 だけ
    both_needed = True
    if not a.force_both and ent and ent.get("both_shell_fp") == info["shell_fp"]:
        both_needed = False
    plan["old_both_shell_fp"] = ent.get("both_shell_fp") if ent else None
    mode = "both" if both_needed else "utf8"
    why = ""
    if info["uncacheable"]:
        why = "常に実行(%s)" % info["uncacheable"][0]
    elif ent is None:
        why = "記録なし" if not a.no_lookup else "キャッシュ無視"
    elif ent.get("status") != "pass":
        why = "前回合格でない"
    elif ent.get("gfp") != gfp:
        why = "共通入力が変化(tools/tests/vendor/環境)"
    elif ent.get("efp") != efp:
        why = "除外指定が変化"
    else:
        # D: リポジトリ側の入力
        if info["full_reasons"] or ent.get("dep_mode") == "full":
            dep_mode = "full"
        else:
            dep_mode = "recorded"
        if info["rw"]:
            dep_hash = rw_hash(memo)
            cur_mode = "rw"
        elif dep_mode == "full" or ent.get("dep_mode") != "recorded":
            dep_hash = full_hash(memo, info["dep_names"])
            cur_mode = "full"
        else:
            dep_hash = paths_hash(memo, ent.get("dep_paths", []))
            cur_mode = "recorded"
        if ent.get("dep_mode") != cur_mode:
            why = "依存の取り方が変化(%s→%s)" % (ent.get("dep_mode"), cur_mode)
        elif ent.get("dep_hash") != dep_hash:
            why = "src等の入力が変化(%s)" % cur_mode
        else:
            mode = "cached"
            plan["cached_entry"] = {k: ent.get(k) for k in ("when", "commit", "dep_mode")}
    plan["mode"] = mode
    plan["why"] = why
    memo.save()
    with open(a.plan_file, "w") as f:
        json.dump(plan, f)
    if mode == "cached":
        e = ent
        print("cached\t%s\t%s\t%s" % (e.get("when", "?"), e.get("commit", "?"),
                                      e.get("dep_mode", "?")))
    else:
        print("%s\t%s" % (mode, why))


def parse_logs(logs):
    started = False
    paths = set()
    for lg in logs:
        try:
            with open(lg, "rb") as f:
                data = f.read().decode("utf-8", "surrogateescape")
        except OSError:
            continue
        for ln in data.split("\n"):
            if not ln:
                continue
            parts = ln.split("\t", 1)
            if parts[0] == "S":
                started = True
            elif parts[0] in ("F", "D") and len(parts) == 2:
                paths.add((parts[0], parts[1]))
    return started, sorted(paths)


def cmd_record(a):
    try:
        with open(a.plan_file) as f:
            plan = json.load(f)
    except Exception:
        die("plan file unreadable")
    script = plan["script"]
    info = plan["info"]
    p = entry_path(script)
    if a.status != "pass" or info["uncacheable"] or a.no_store:
        try:
            os.unlink(p)
        except OSError:
            pass
        print("not-stored")
        return
    memo = Memo()
    gfp, _ = global_fp(memo)
    if gfp != plan["gfp"]:
        try:
            os.unlink(p)
        except OSError:
            pass
        print("not-stored(実行中に tools/vendor/環境 が変化した)")
        memo.save()
        return
    started, paths = parse_logs(a.logs)
    paths = sorted(set(paths) | set(("F", p) for p in info.get("static_paths", [])))
    reasons = list(info["full_reasons"])
    if info["uses_python"] and not started:
        reasons.append("python フックの起動記録が無い")
    if reasons:
        dep_mode = "full"
    else:
        dep_mode = "recorded"
    if info["rw"]:
        dep_mode = "rw"
        dep_hash = rw_hash(memo)
    elif dep_mode == "full":
        dep_hash = full_hash(memo, info["dep_names"])
    else:
        dep_hash = paths_hash(memo, paths)
    ent = {
        "ver": VERSION, "script": script, "status": "pass",
        "when": time.strftime("%Y-%m-%d %H:%M"), "commit": head_commit(),
        "gfp": plan["gfp"], "efp": plan["efp"], "shell_fp": plan["shell_fp"],
        "both_shell_fp": plan["shell_fp"] if a.mode == "both"
        else plan.get("old_both_shell_fp"),
        "dep_mode": dep_mode, "dep_hash": dep_hash,
        "dep_paths": [list(x) for x in paths] if dep_mode == "recorded" else [],
        "full_reasons": reasons[:3],
    }
    # 保存前に依存が実行中に動いていないかを確かめる（動いていたら保存しない）
    if dep_mode == "recorded":
        again = paths_hash(memo, paths)
    elif dep_mode == "rw":
        again = rw_hash(memo)
    else:
        again = full_hash(memo, info["dep_names"])
    if again != dep_hash:
        try:
            os.unlink(p)
        except OSError:
            pass
        print("not-stored(実行中にリポジトリ側の入力が変化した)")
        memo.save()
        return
    os.makedirs(cache_dir(), exist_ok=True)
    tmp = p + ".%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(ent, f)
    os.replace(tmp, p)
    memo.save()
    print("stored\t%s" % dep_mode)


# ---------------------------------------------------------------- lint
VAR_NONASCII_RE = re.compile(r"\$(?:\{)?[A-Za-z_][A-Za-z0-9_]*(?<!\})(?=[^\x00-\x7f])")


def strip_single_quotes(line):
    out = []
    inq = False
    dq = False
    i = 0
    while i < len(line):
        c = line[i]
        if not inq and c == "\\":
            out.append(line[i:i + 2])
            i += 2
            continue
        if not dq and c == "'":
            inq = not inq
            i += 1
            continue
        if not inq and c == '"':
            dq = not dq
        if not inq:
            out.append(c)
        i += 1
    return "".join(out)


def lint_text(text):
    hits = []
    for no, ln in shell_logical_lines(text):
        if "cleanroom-lint:ignore" in ln:
            continue
        s = strip_single_quotes(ln)
        if "#" in s:
            # 引用符の外のコメントだけ落とす簡易処理
            m = re.search(r"(?:^|\s)#", s)
            if m:
                s = s[:m.start()]
        for m in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)(?=[^\x00-\x7f])", s):
            hits.append((no, m.group(0) + s[m.end():m.end() + 1]))
    return hits


def cmd_lint(a):
    bad = 0
    n = 0
    for dp, dns, fns in os.walk(os.path.join(REPO, "tools")):
        dns[:] = sorted(d for d in dns if d not in SKIP_NAMES)
        for fn in sorted(fns):
            if not fn.endswith(".sh"):
                continue
            p = os.path.join(dp, fn)
            n += 1
            for no, frag in lint_text(read_text(p)):
                bad += 1
                print("  %s:%d: $変数の直後に非ASCII文字: %s"
                      % (os.path.relpath(p, REPO), no, frag))
    print("対象 %d 本、検出 %d 件" % (n, bad))
    sys.exit(1 if bad else 0)


def cmd_clear(a):
    d = cache_dir()
    if os.path.isdir(d):
        for n in os.listdir(d):
            if n.startswith("e-") or n == "memo.json":
                try:
                    os.unlink(os.path.join(d, n))
                except OSError:
                    pass
    print("cleared")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("gfp")
    s = sp.add_parser("analyze")
    s.add_argument("script")
    s = sp.add_parser("plan")
    s.add_argument("script")
    s.add_argument("--plan-file", required=True)
    s.add_argument("--no-lookup", action="store_true")
    s.add_argument("--force-both", action="store_true")
    s = sp.add_parser("record")
    s.add_argument("--plan-file", required=True)
    s.add_argument("--status", required=True)
    s.add_argument("--mode", default="both")
    s.add_argument("--no-store", action="store_true")
    s.add_argument("--logs", nargs="*", default=[])
    sp.add_parser("lint")
    sp.add_parser("clear")
    a = ap.parse_args()
    if a.cmd == "gfp":
        memo = Memo()
        g, comp = global_fp(memo)
        memo.save()
        print(g)
        if os.environ.get("PC88_RUNALL_DEBUG"):
            print(json.dumps(comp, indent=1), file=sys.stderr)
    elif a.cmd == "analyze":
        print(json.dumps(analyze(a.script), ensure_ascii=False, indent=1))
    elif a.cmd == "plan":
        cmd_plan(a)
    elif a.cmd == "record":
        cmd_record(a)
    elif a.cmd == "lint":
        cmd_lint(a)
    elif a.cmd == "clear":
        cmd_clear(a)


if __name__ == "__main__":
    main()
