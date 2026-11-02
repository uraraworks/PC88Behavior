# B58: スペースのあとに別のキーで G1 が進むかを測る — 結果

記録日: 2026-11-02
規則: [b58-g1-more-keys-preregistration.md](b58-g1-more-keys-preregistration.md) どおり。測定はクラウドの実行環境で rc=0。画像と画面本文は開いていない。記録は `measurements/b58-g1-more-keys.txt`。

## 結果

```
arm D untypable=0 oo=same image=differ text=same cross=71 71 fc=112687 112683 first-cross-pc=none
arm L untypable=0 oo=same image=differ text=same cross=71 87 fc=112687 124721 first-cross-pc=none
arm C untypable=0 oo=same image=same text=same cross=71 71 fc=112687 112683 first-cross-pc=none
arm F untypable=0 oo=same image=differ text=same cross=72 72 fc=112689 112685 first-cross-pc=none
arm E untypable=0 oo=same image=differ text=same cross=71 71 fc=112687 112683 first-cross-pc=none
arm T untypable=0 oo=same image=differ text=same cross=71 71 fc=112687 112683 first-cross-pc=none
```

## 読み方

事前登録の判定どおり、公式の `cross` が 71 より増える腕を「進む腕」とする。上の行をそのまま根拠にする。
