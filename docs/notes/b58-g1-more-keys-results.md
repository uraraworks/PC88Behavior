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

**新しい違いが出た。**

- 公式どうしは全腕で同じである
- 腕 F は公式の移る回数が 72 に増える（進む腕）。自作も 72 で同じだが、画像は違う
- 腕 L は公式 71、**自作 87** で、自作だけ先へ進む
- 腕 D、F、E、T、L は、テキストは同じで**画像が違う**。腕 C だけ全部同じである
- 移る先が違う番号はまだ無い

キーの読み方か、キーに応じた描画の違いと考える（**推定**）。B60 でどのキーが効くかを 1 つずつ測る。
