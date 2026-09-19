; src/ext_bank/bank0.asm — 拡張ROMバンク0(N88_0.ROM)。土台のみ、機能無し。
;
; docs/spec/ext-rom-bank.md 第0節「位置づけ(実装スコープ)」配置案C:
; 既存モジュールの配置は動かさず、新しい機能だけをバンクへ新設する方針。
; 今回はバンク切り替えの仕組みそのものを固める段階のため、各バンクの
; 中身は固定値を返す試験ルーチン(自己検査用)だけ。新しいBASICの機能は
; まだ置かない。
;
; 0x6000(窓の先頭)を起点にORGする。src/ext_bank/make_ext_rom_banks.pyが
; アセンブル後、先頭0x6000バイトの空き(ORGによる詰め物)を切り落として
; 8KBのバンクファイルにする。バンク側コードが絶対番地のJP・CALL・
; データ参照(下記EXT_BANK0_ABS_TEST_ENTRY)を使うようになった場合、
; その番地は「実際に窓として見える番地(0x6000-0x7FFF)」でエンコード
; されていなければならない——この2つのORG(0x6000・0x6010)を0始まりに
; 書き換えると、絶対番地参照だけが実行時の番地(常に0x6000起点)とズレて
; 誤動作する(固定値を返すだけのEXT_BANK0_TEST_ENTRYのようなPC相対命令
; 〈RET等〉だけの試験ルーチンでは、たまたまズレが顕在化しない——これが
; 絶対番地参照の試験ルーチンを別に用意した理由)。
; 故障注入(--inject-no-org-fault、自己検査の陰性対照専用)は
; make_ext_rom_banks.pyがこの2行のORGをテキスト置換で0始まりへ書き換えて
; 組み立て、この前提を破る。
    ORG 0x6000
EXT_BANK0_TEST_ENTRY:
    LD A,0xB0
    RET

; 絶対番地の試験(オフセット0x10に固定。呼び出し側〈src/ext_bank/
; relay.asmのEXT_BANK0_ABS_ENTRY_OFFSET〉と合わせる)。CALL・JP・
; LD A,(nn)がいずれも絶対番地でエンコードされるため、ORGが実際の窓の
; 番地(0x6000)と違えば違う番地へ飛ぶ/違うデータを読む。
    ORG 0x6010
EXT_BANK0_ABS_TEST_ENTRY:
    CALL EXT_BANK0_ABS_HELPER    ; 絶対番地CALL
    JP EXT_BANK0_ABS_CHECK       ; 絶対番地JP

EXT_BANK0_ABS_HELPER:
    RET

EXT_BANK0_ABS_CHECK:
    LD A,(EXT_BANK0_ABS_TABLE)   ; 絶対番地のデータ参照
    RET

EXT_BANK0_ABS_TABLE:
    DB 0xC5
