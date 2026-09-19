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

; =======================================================================
; EXT_BANK0_SQR_ENTRY（オフセット0x80固定） — 単精度SQR本体。
;
; 根拠: docs/spec/l4-program.md 第4.16b節「SQRは(GW-BASICの反復手順が
; 未特定なため)候補間で差が出ない」——つまり実装手順そのものは仕様書の
; 対象外で、正しく丸めた(round-to-nearest、タイは理論上到達しない)
; 単精度平方根を返しさえすれば適合する。ここでは倍精度(56bit仮数)の
; ニュートン法で単精度(24bit)の2倍以上のガードbitを確保してから
; 常駐部のMBF_DTOS($CSD丸め、既存の他機能で適合済み)へ渡す
; ——2段丸め(倍精度→単精度)が問題になるのは中間精度が目的精度の
; 2倍+αに満たない場合だけであり、56bit≫24bit*2なのでここでは
; 発生しない(l4-basic.md 5.3a節の丸め規則とは無関係、CSD自体の丸め
; 方式を変えていない)。
;
; 入力: MBF_OPA(単精度、呼び出し前に0以上であることを呼び出し元
;   〈interp.asm FTNF_DO_SQR〉が確認済み——ゼロ・負はここに来る前に
;   分岐している)。
; 出力: MBF_RES(単精度4byte、mbf_single.asmと共有の外部形式)。
; 破壊: 全レジスタ。
;
; 呼び先の常駐ルーチン(MBF_STOD/MBF_DADD/MBF_DDIV/MBF_DTOS、
; mbf_double.asm)は、docs/spec/ext-rom-bank.md 第2節 制約3(a)〜(c)の
; 条件を満たす(いずれも窓の外・0x71/0x32へ触れない・1回CALLされて
; RETで戻るだけ)。各ADDR定数はbuild_main_rom.pyが実測アドレスへ
; テキスト置換する(EXT_BANK0_MBF_TEST_ENTRYのMBF_ADD_ADDRと同じ手法)。
; =======================================================================
MBF_STOD_ADDR EQU 0x1787
MBF_DADD_ADDR EQU 0x1787
MBF_DDIV_ADDR EQU 0x1787
MBF_DTOS_ADDR EQU 0x1787

; mbf_double.asmのMBF_DOPA/MBF_DOPB/MBF_DRES(8byte、外部形式)。
; bank0.asmはmbf_double.asmをINCLUDEしないため、番地はEQUで直接持つ
; （mbf_double.asmヘッダのMBF_DOUBLE_RAM_BASE=0xC200と同じ値、
; 密結合はコメントで明示——ズレれば自己検査ではなく実機能そのものが
; 不一致になる。将来この番地を動かす場合はここも合わせて直す）。
MBF_DOPA_RAM EQU 0xC200
MBF_DOPB_RAM EQU 0xC208
MBF_DRES_RAM EQU 0xC210

; SQR専用の作業域(倍精度8byte×2)。mbf_single.asm(0xC000-0xC169)にも
; mbf_double.asm(0xC200-0xC2AC)にも重ならない0xC300以降を使う
; (仕様書に無い判断ではなく、両ファイルのコメントにある「衝突しない
; 空きを選ぶ」方針の踏襲)。
SQR_X EQU 0xC300   ; ニュートン法の間、常に元の値xを保持(8byte)
SQR_Y EQU 0xC308   ; ニュートン法の現在の近似値y(8byte)
SQR_ITER_LEFT EQU 0xC310   ; 残り反復回数(1byte、レジスタ渡しは
                           ; 常駐呼び出しで潰れるためRAMに置く)

SQR_ITER_COUNT EQU 10   ; 初期誤差<=sqrt(2)(高々1bit)からの2次収束。
                         ; 56bit(倍精度仮数)まで2^10=1024倍の余裕を
                         ; 見込み、単精度(24bit)への丸めに十分な
                         ; ガードbitを確保する。

    ORG 0x6080
EXT_BANK0_SQR_ENTRY:
    CALL MBF_STOD_ADDR          ; MBF_OPA(単精度) -> MBF_DRES(倍精度、厳密)
    LD HL,MBF_DRES_RAM
    LD DE,SQR_X
    LD BC,8
    LDIR                         ; SQR_X = x(倍精度)

    ; 初期値y0 = 2^k (k = floor((単精度指数バイト-128)/2))。
    ; MBF指数バイトの規約はvalue=frac*2^(e-128)・frac∈[0.5,1)なので、
    ; 仮数0(=frac=0.5、暗黙の先頭1だけ)のときvalue=0.5*2^(e-128)=2^(e-129)。
    ; value=2^kにしたいので e=k+129(l4_sqr_bank_conformのデバッグで
    ; +128は1bit不足〈y0が真値の半分〉と判明、収束はしても無駄なので
    ; +129に直した)。
    LD A,(MBF_OPA+3)             ; 単精度の指数バイト(128げた上げ)
    SUB 128                      ; A = e-128 (符号付き)
    SRA A                        ; A = floor((e-128)/2) (2の補数の算術右シフト)
    ADD A,129                    ; A = k+129 = y0の指数バイト
    LD (SQR_Y+7),A
    XOR A
    LD (SQR_Y),A
    LD (SQR_Y+1),A
    LD (SQR_Y+2),A
    LD (SQR_Y+3),A
    LD (SQR_Y+4),A
    LD (SQR_Y+5),A
    LD (SQR_Y+6),A                ; 符号0・仮数上位7bit=0(仮数全体0=1.0)

    LD A,SQR_ITER_COUNT
    LD (SQR_ITER_LEFT),A
_sqr_loop:
    ; MBF_DDIVはMBF_DOPA/MBF_DOPB(=DOPA/DOPB)を計算するので、x/yを得る
    ; にはMBF_DOPA=x・MBF_DOPB=yの順で置く(l4_sqr_bank_conformの
    ; デバッグで、この2つを逆に置いていたバグ(y/xを計算していた)を発見)。
    LD HL,SQR_X
    LD DE,MBF_DOPA_RAM
    LD BC,8
    LDIR
    LD HL,SQR_Y
    LD DE,MBF_DOPB_RAM
    LD BC,8
    LDIR
    CALL MBF_DDIV_ADDR            ; MBF_DRES = x/y

    ; MBF_DOPA=y, MBF_DOPB=(直前の結果t) -> MBF_DADD -> MBF_DRES = y+t
    LD HL,SQR_Y
    LD DE,MBF_DOPA_RAM
    LD BC,8
    LDIR
    LD HL,MBF_DRES_RAM
    LD DE,MBF_DOPB_RAM
    LD BC,8
    LDIR
    CALL MBF_DADD_ADDR

    ; 2で割る(指数バイトを1減らすだけ、厳密。0除算になるほど小さい値には
    ; 実用上届かないため指数0のガードは省略しない——安全側に1つ用意する)。
    LD A,(MBF_DRES_RAM+7)
    OR A
    JR Z,_sqr_skip_halve
    DEC A
    LD (MBF_DRES_RAM+7),A
_sqr_skip_halve:
    LD HL,MBF_DRES_RAM
    LD DE,SQR_Y
    LD BC,8
    LDIR                          ; SQR_Y = 新しいy

    LD A,(SQR_ITER_LEFT)
    DEC A
    LD (SQR_ITER_LEFT),A
    JR NZ,_sqr_loop

    ; 収束したSQR_Yを単精度へ($CSD丸め)
    LD HL,SQR_Y
    LD DE,MBF_DOPA_RAM
    LD BC,8
    LDIR
    JP MBF_DTOS_ADDR              ; MBF_RESへ書いてRET(MBF_DTOSが戻り先で戻る)
