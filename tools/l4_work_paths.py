"""器具CLIの既存許可根と、自作照合入口が明示した外部作業根。"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV = 'PC88_L4_CONFORM_ALLOWED_ROOT'


def allowed_path(path, roots):
    if not path.is_absolute():
        return False
    resolved = path.resolve()
    if any(resolved.is_relative_to(root.resolve()) for root in roots):
        return True
    value = os.environ.get(ENV)
    if not value:
        return False
    root = Path(value)
    # 相対指定、ファイルシステム全体、リポジトリ内への権限拡張は拒否。
    if not root.is_absolute():
        return False
    root = root.resolve()
    if root == Path(root.anchor) or root == REPO or REPO in root.parents or root in REPO.parents:
        return False
    return resolved.is_relative_to(root)
