# frozen_tree.sh — 過去の測定・事前登録の凍結値を検査する selftest が source して使う。
# 凍結値は「その測定で使った ROM」の記録なので、値は変えず、比較相手を
# 凍結値を作ったコミットを git archive で取り出したソース木に替える
# （先例: 9d716ce, disk_read_chr_selftest.sh）。現在の作業ツリーの実装が
# 進んで ROM が変わっても、凍結値との一致は当時のソースで確かめられる。
# キャッシュはしない（毎回取り出してビルドし、古い成果物に偽られない）。
#
# 使い方: use_frozen_tree <commit> <work-dir>
#   REPO を、そのコミットを取り出した木（<work-dir>/frozen-root/PC88Behavior）に差し替える。
#   build_main_rom.py はvendor/をリポジトリの一段上の兄弟として参照するので同じ相対位置を再現する。
#   元の作業ツリーは REPO_WORKTREE に残す。
use_frozen_tree() {
  local commit="$1" work="$2"
  REPO_WORKTREE="$REPO"
  local root="$work/frozen-root"
  mkdir -p "$root/PC88Behavior"
  ln -s "$REPO_WORKTREE/../vendor" "$root/vendor"
  git -C "$REPO_WORKTREE" archive "$commit" | tar -x -C "$root/PC88Behavior"
  REPO="$root/PC88Behavior"
}

# use_frozen_checkout <commit> <work-dir>
#   use_frozen_tree と同じだが、.git のある木（git clone --shared 後に detached checkout）にする。
#   照合器自身が `git -C $REPO archive <別コミット>` を呼ぶ場合（check_m6ik_gates.py の G6）用。
#   ネットワーク不要（ローカル共有クローン）。
use_frozen_checkout() {
  local commit="$1" work="$2"
  REPO_WORKTREE="$REPO"
  local root="$work/frozen-root"
  mkdir -p "$root"
  ln -s "$REPO_WORKTREE/../vendor" "$root/vendor"
  git clone -q --shared --no-checkout "$REPO_WORKTREE" "$root/PC88Behavior"
  git -C "$root/PC88Behavior" checkout -q --detach "$commit"
  REPO="$root/PC88Behavior"
}
