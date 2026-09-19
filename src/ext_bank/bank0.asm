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

; ---------------------------------------------------------------
; EXT_BANK0_MBF_TEST_ENTRY(オフセット0x30固定) — 「バンク0の試験ルーチン
; が常駐の単精度演算を呼んで正しい結果を返す」自己検査
; (docs/spec/ext-rom-bank.md 第2節 制約3、docs/notes/
; ext2-relay-to-resident-results.md で測定済みの範囲)。
;
; MBF_OPA=1.0・MBF_OPB=2.0(src/l4_basic/mbf_single.asmのMBF単精度4バイト
; 表現、番地は同ファイルの固定EQU)を置いてから常駐部のMBF_ADDを1回CALLし、
; 結果MBF_RESが3.0(00 00 40 82)と一致するかを返す。
;
; MBF_ADD_ADDR: 常駐部(N88.ROM)側のMBF_ADDの実アドレス。バンクは
; N88.ROMと独立にアセンブルされる(make_ext_rom_banks.py)ため、この値は
; build_main_rom.pyが実測したアドレスでテキスト置換する
; (--mbf-add-addr、既定値は現在のモジュール配置での実測値)。ズレて
; いれば呼び出し先が変わり、この自己検査が不一致(またはハング)を検出
; する——密結合を隠さず、崩れたら検出できる形にしてある。
MBF_ADD_ADDR EQU 0x1787
MBF_OPA EQU 0xC000
MBF_OPB EQU 0xC004
MBF_RES EQU 0xC008

    ORG 0x6030
EXT_BANK0_MBF_TEST_ENTRY:
    XOR A
    LD (MBF_OPA),A
    LD (MBF_OPA+1),A
    LD (MBF_OPA+2),A
    LD A,0x81               ; 1.0
    LD (MBF_OPA+3),A

    XOR A
    LD (MBF_OPB),A
    LD (MBF_OPB+1),A
    LD (MBF_OPB+2),A
    LD A,0x82               ; 2.0
    LD (MBF_OPB+3),A

    CALL MBF_ADD_ADDR       ; 常駐部(窓の外)のMBF_ADDを1回CALLして戻る

    ; 期待値3.0 = 00 00 40 82
    LD A,(MBF_RES)
    OR A
    JR NZ,_eb0mbf_ng
    LD A,(MBF_RES+1)
    OR A
    JR NZ,_eb0mbf_ng
    LD A,(MBF_RES+2)
    CP 0x40
    JR NZ,_eb0mbf_ng
    LD A,(MBF_RES+3)
    CP 0x82
    JR NZ,_eb0mbf_ng
    LD A,1
    RET
_eb0mbf_ng:
    XOR A
    RET
