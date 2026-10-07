# tools/runall_hook/sitecustomize.py — run_all_selftests.sh の入力キャッシュ用の
# 「読んだ入力ファイルの記録」フック。
#
# run_all_selftests.sh が PYTHONPATH の先頭にこのディレクトリを足し、環境変数
#   PC88_RUNALL_LOG   記録の追記先（行: "S<TAB>pid" 起動印 / "F<TAB>相対パス" /
#                     "D<TAB>相対パス"）
#   PC88_RUNALL_ROOT  リポジトリのルート（絶対パス）
# を渡したときだけ有効になる。無ければ何もしない（普段のpython起動に影響しない）。
#
# 記録するもの: ルート配下（tools/ tests/ .git private __pycache__ を除く）への
#   open / os.open / stat / lstat / access（F: 内容を見る・存在を見る）
#   listdir / scandir（D: 名前の並びを見る）
# import による読み込みも posix.stat と _io.open_code を通るので記録される。
# 記録のためにファイルの中身は読まない。パスだけを書く。
#
# PC88_RUNALL_HOOK_MARKER（chain が他のフックを見分ける目印）
# 注意: 既存の sitecustomize（Homebrew版pythonが持っている）を隠さないよう、
# このファイルの後で本来の sitecustomize を探して実行する。
import os as _os
import sys as _sys


def _chain():
    here = _os.path.dirname(_os.path.abspath(__file__))
    for p in list(_sys.path):
        d = _os.path.abspath(p or ".")
        if d == here:
            continue
        cand = _os.path.join(d, "sitecustomize.py")
        if _os.path.isfile(cand):
            try:
                with open(cand, "rb") as fh:
                    if b"PC88_RUNALL_HOOK_MARKER" in fh.read(4096):
                        continue  # 入れ子実行で重なった別のフックは飛ばす
            except OSError:
                pass
            import importlib.util as u
            spec = u.spec_from_file_location("_real_sitecustomize", cand)
            m = u.module_from_spec(spec)
            spec.loader.exec_module(m)
            return


def _install():
    import builtins as _b
    if getattr(_b, "_pc88_runall_hooked", False):
        return  # 入れ子実行で二重に仕込まない
    log = _os.environ.get("PC88_RUNALL_LOG")
    root = _os.environ.get("PC88_RUNALL_ROOT")
    if not log or not root:
        return
    import posix
    import builtins
    import io
    import _io

    _b._pc88_runall_hooked = True
    fd = posix.open(log, posix.O_WRONLY | posix.O_APPEND | posix.O_CREAT, 0o644)
    roots = {root.rstrip("/")}
    try:
        roots.add(_os.path.realpath(root).rstrip("/"))
    except Exception:
        pass
    skip_top = ("tools", "tests", ".git", "private")
    seen = set()
    getcwd = posix.getcwd
    normpath = _os.path.normpath
    write = posix.write

    def emit(kind, p):
        try:
            if isinstance(p, int):
                return
            p = _os.fspath(p)
            if isinstance(p, bytes):
                p = p.decode("utf-8", "surrogateescape")
            if not p.startswith("/"):
                p = getcwd() + "/" + p
            p = normpath(p)
            for r in roots:
                if p == r or p.startswith(r + "/"):
                    rel = p[len(r) + 1:]
                    break
            else:
                return
            if rel == "" or "__pycache__" in rel:
                return
            top = rel.split("/", 1)[0]
            if top in skip_top:
                return
            key = (kind, rel)
            if key in seen:
                return
            seen.add(key)
            write(fd, (kind + "\t" + rel + "\n").encode("utf-8", "surrogateescape"))
        except Exception:
            pass

    write(fd, ("S\t%d\n" % posix.getpid()).encode())

    def wrap(fn, kind):
        def w(*a, **k):
            if a:
                emit(kind, a[0])
            else:
                emit(kind, k.get("path", k.get("file", ".")))
            return fn(*a, **k)
        w.__name__ = getattr(fn, "__name__", "w")
        w.__doc__ = getattr(fn, "__doc__", None)
        return w

    sets = [getattr(_os, n) for n in ("supports_dir_fd", "supports_fd",
                                      "supports_follow_symlinks",
                                      "supports_effective_ids")]

    def patch_posix(n, kind):
        orig = getattr(posix, n)
        f = wrap(orig, kind)
        for st in sets:
            if orig in st:
                st.discard(orig)
                st.add(f)
        setattr(posix, n, f)
        setattr(_os, n, f)

    builtins.open = wrap(builtins.open, "F")
    io.open = builtins.open
    patch_posix("open", "F")
    for n in ("stat", "lstat", "access"):
        patch_posix(n, "F")
    for n in ("listdir", "scandir"):
        patch_posix(n, "D")
    f = wrap(_io.open_code, "F")
    _io.open_code = f
    io.open_code = f


_chain()
try:
    _install()
except Exception:
    pass
