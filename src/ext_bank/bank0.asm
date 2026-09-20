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
; 2026-09-20追記(ATN/EXP/LOG、第4.16b節): MBF_STATUS(EXPのオーバーフロー
; 信号)・MBF_OUT_CMP(ATN/LOGのMBF_CMP結果)・MBF_IN_INT(LOGのe_raw→
; MBF_INT_TO_SINGLE入力)。mbf_single.asmの同名EQUと同じ値(密結合は
; コメントで明示、MBF_OPA等と同じ方針)。
MBF_STATUS EQU 0xC00C
MBF_IN_INT EQU 0xC00D
MBF_OUT_CMP EQU 0xC00F

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

; =======================================================================
; SIN/COS/TAN(単精度、2026-09-20追記) — docs/spec/l4-program.md 第4.16a節
; (`l4-s6b`〜`l4-s6g`で確定した候補M9)。
;
; 手順(第4.16a節): 範囲縮約(x*(1/2π)の小数部)・多項式評価(Horner、
; SINCN係数)いずれも単精度で行い、内部の単精度演算(乗算・加算・減算・
; 除算すべて)は常駐部(mbf_single.asm)のMBF_ADD/MBF_SUB/MBF_MUL/MBF_DIV
; の丸め(away、既定でaway丸めに統一済み——mbf_single.asm該当コメント
; 「2026-09-20追記(l4-s7a・l4-s7b)」参照)にそのまま従う。演算そのものを
; 再実装せず、常駐ルーチンをdocs/spec/ext-rom-bank.md 第2節 制約3の
; 条件下でCALLする(SQRのMBF_STOD/MBF_DADD/MBF_DDIV/MBF_DTOS呼び出しと
; 同じ手法)。
;
; 係数・定数の出所はtools/l4_mbf_oracle_v3.py(GW-BASIC MIT公開ソース
; MATH1.ASMのインライン即値を8進DB列のまま起こしたもの、コメントに
; 行番号を明記——係数の当てはめは行っていない)。floor(床関数)は
; 常駐部のTRUNC_TO_SINGLE(0方向への切り捨て)を、本ルーチンの呼び出し
; 箇所ではいずれも被演算子が非負(範囲縮約後のfrac_turnsは[0,1)、
; quad=frac_turns*4は[0,4)のいずれも非負)であることが構造上保証されて
; いるため、0方向切り捨て=floorとしてそのまま使う(FTNF_DO_INTのような
; 負数側の補正は不要)。
; =======================================================================

; 常駐部アドレス(build_main_rom.pyが実測アドレスへテキスト置換する、
; EXT_BANK0_MBF_TEST_ENTRY/EXT_BANK0_SQR_ENTRYと同じ手法。プレースホルダ
; の値0x1787はmake_ext_rom_banks.pyのGENERIC_ADDR_PLACEHOLDERと一致させる
; 必要があり、実際の値ではない)。
SIN_ADD_ADDR EQU 0x1787
SIN_SUB_ADDR EQU 0x1787
SIN_MUL_ADDR EQU 0x1787
SIN_DIV_ADDR EQU 0x1787
SIN_NEG_ADDR EQU 0x1787
SIN_TRUNC_ADDR EQU 0x1787

; 作業域(単精度4byte、mbf_single.asm(0xC000-0xC169付近)・
; mbf_double.asm(0xC200-0xC2AC付近)・EXT_BANK0_SQR_ENTRYの作業域
; (SQR_X/SQR_Y/SQR_ITER_LEFT、0xC300-0xC310)のいずれとも重ならない
; 0xC320以降を使う(同ファイルのSQR作業域コメントにある「衝突しない
; 空きを選ぶ」方針の踏襲)。
SC_X       EQU 0xC320   ; |x|(単精度、範囲縮約の入力)
SC_Y       EQU 0xC324   ; x*IN2PI_SINGLE
SC_N       EQU 0xC328   ; floor(SC_Y)
SC_FRAC    EQU 0xC32C   ; 範囲縮約結果(frac_turns、[0,1))
SC_QUAD    EQU 0xC330   ; frac_turns*4([0,4))
SC_QNUM    EQU 0xC334   ; floor(SC_QUAD)(0/1/2/3のいずれか、単精度表現のまま)
SC_SUB     EQU 0xC338   ; quad-q_num(象限内の位置、[0,1))
SC_REDUCED EQU 0xC33C   ; SC_SUB/4(多項式評価・微小角判定の入力)
SC_X2      EQU 0xC340   ; SC_REDUCED^2(Horner多項式の変数)
SC_ACC     EQU 0xC344   ; Horner多項式評価のアキュムレータ
SC_RESULT  EQU 0xC348   ; sin本体の結果(象限・外側符号の反転前後で共有)
SC_TMP_A   EQU 0xC34C   ; COS用一時領域(x+PI2)
SC_TAN_X   EQU 0xC350   ; TAN用: 元のxの退避(SIN/COSがMBF_OPAを上書きするため)
SC_SINVAL  EQU 0xC354   ; TAN用: sin(x)の保存
SC_COSVAL  EQU 0xC358   ; TAN用: cos(x)の保存
SC_Q       EQU 0xC35C   ; 象限(0-3、1byte)
SC_NEG     EQU 0xC35D   ; outer_neg(0/1、1byte)

; 定数(単精度4byte、tools/l4_mbf_oracle_v3.py・v5_m5.pyの値をそのまま
; バイト列化。出所は各定数のコメントを参照——GW-BASIC MIT公開ソース
; MATH1.ASMのインライン即値、8進DB列を10進/16進へ変換しただけで係数の
; 当てはめは行っていない)。
SC_IN2PI_SINGLE:
    DB 0x83,0xF9,0x22,0x7E   ; 1/(2π)を単精度へ丸めたもの(force_to_single、
                              ; MATH1.ASM 892-899 $IN2PIの単精度版、
                              ; l4_mbf_oracle_v5_m5.py IN2PI_SINGLE)
SC_ONE_SINGLE:
    DB 0x00,0x00,0x00,0x81   ; 1.0(単精度)
SC_TWO_PI:
    DB 0xDB,0x0F,0x49,0x83   ; 2π(MATH1.ASM 1036-1037 SIN60)
SC_PI2:
    DB 0xDB,0x0F,0x49,0x81   ; π/2(MATH1.ASM 1137-1138 ATN100)
SC_SINCN0:
    DB 0xFB,0xD7,0x1E,0x86   ; MATH1.ASM 831-856 $SINCN(Hart #3341)、5係数
SC_SINCN1:
    DB 0x65,0x26,0x99,0x87
SC_SINCN2:
    DB 0x58,0x34,0x23,0x87
SC_SINCN3:
    DB 0xE1,0x5D,0xA5,0x86
SC_SINCN4:
    DB 0xDB,0x0F,0x49,0x83

; ---------------------------------------------------------------------
; EXT_BANK0_SIN_ENTRY(オフセット0x0200固定)・EXT_BANK0_COS_ENTRY
; (0x0210固定)・EXT_BANK0_TAN_ENTRY(0x0220固定) — interp.asm
; FTNF_DO_SIN/COS/TANがEXT_BANK_CALL(bank=0)で呼ぶ。
; 入力: MBF_OPA=単精度x(呼び出し元がVAL_LOAD_CUR_TO_OPAで設定済み)。
; 出力: MBF_RES=単精度sin(x)/cos(x)/tan(x)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
    ORG 0x6200
EXT_BANK0_SIN_ENTRY:
    CALL SC_SIN_IMPL
    RET

    ORG 0x6210
EXT_BANK0_COS_ENTRY:
    CALL SC_COS_IMPL
    RET

    ORG 0x6220
EXT_BANK0_TAN_ENTRY:
    CALL SC_TAN_IMPL
    RET

; ---------------------------------------------------------------------
; EXT_BANK0_ATN_ENTRY(オフセット0x0230固定)・EXT_BANK0_EXP_ENTRY
; (0x0240固定)・EXT_BANK0_LOG_ENTRY(0x0250固定、いずれも2026-09-20
; 追記) — interp.asm FTNF_DO_ATN/EXP/LOGがEXT_BANK_CALL(bank=0)で呼ぶ。
; 入力: MBF_OPA=単精度x(呼び出し元がVAL_LOAD_CUR_TO_OPAで設定済み)。
; 出力: MBF_RES=結果。EXPのみMBF_STATUS(0=正常/1=オーバーフロー)も見る。
; 破壊: 全レジスタ。AEL_ATN_IMPL/AEL_EXP_IMPL/AEL_LOG_IMPL(実装本体、
; 定数・作業域含む)はSIN/COS/TANの実装本体(SC_COPY4以降)より後ろに
; 置く(前方参照、SC_SIN_ENTRYがSC_SIN_IMPLを前方参照するのと同じ手法)
; ——SIN/COS/TANの4つのORG(0x6200/0x6210/0x6220)と同じく、この3つの
; ORGも実装本体より前(TAN_ENTRYの直後)に固定オフセットで置かないと、
; 実装本体の分量次第で「ORGが既に書いた領域より手前を指す」アセンブル
; エラーになる(2026-09-20の実装時に実際に踏んだ)。
; ---------------------------------------------------------------------
    ORG 0x6230
EXT_BANK0_ATN_ENTRY:
    CALL AEL_ATN_IMPL
    RET

    ORG 0x6240
EXT_BANK0_EXP_ENTRY:
    CALL AEL_EXP_IMPL
    RET

    ORG 0x6250
EXT_BANK0_LOG_ENTRY:
    CALL AEL_LOG_IMPL
    RET

; ---------------------------------------------------------------------
; 共通ヘルパ(4byte単精度値のコピー)。
; ---------------------------------------------------------------------
SC_COPY4:                 ; HL=src, DE=dst -> 4byteコピー。破壊: AF,BC,HL,DE
    LD BC,4
    LDIR
    RET

SC_SET_OPA:                ; HL=src(4byte) -> MBF_OPA。破壊: AF,BC,HL,DE
    LD DE,MBF_OPA
    JP SC_COPY4

SC_SET_OPB:                ; HL=src(4byte) -> MBF_OPB。破壊: AF,BC,HL,DE
    LD DE,MBF_OPB
    JP SC_COPY4

SC_GET_RES:                ; DE=dst(4byte) <- MBF_RES。破壊: AF,BC,HL
    LD HL,MBF_RES
    JP SC_COPY4

; ---------------------------------------------------------------------
; SC_QNUM_TO_Q — SC_QNUM(floor(quad)、値は0/1/2/3のいずれか、単精度の
;   まま厳密に表現できる整数)を0-3のZ80整数へ変換し(SC_Q)へ書く。
;   厳密値なので丸め不要、指数バイトとbit判定だけの分岐で足りる
;   (0=exp0、1=exp0x81、2/3=exp0x82でmantissa上位ビットの有無で判別。
;   tools/l4_mbf_oracle_v2.py GwNum.from_fraction(0/1/2/3,"single")の
;   実際のバイト列から確認した値)。破壊: AF。
; ---------------------------------------------------------------------
SC_QNUM_TO_Q:
    LD A,(SC_QNUM+3)
    OR A
    JP Z,_sc_q2q_0
    CP 0x81
    JP Z,_sc_q2q_1
    LD A,(SC_QNUM+2)
    AND 0x40
    JP Z,_sc_q2q_2
    LD A,3
    JP _sc_q2q_store
_sc_q2q_2:
    LD A,2
    JP _sc_q2q_store
_sc_q2q_1:
    LD A,1
    JP _sc_q2q_store
_sc_q2q_0:
    LD A,0
_sc_q2q_store:
    LD (SC_Q),A
    RET

; ---------------------------------------------------------------------
; SC_RR_REDUCE — 範囲縮約(第4.16a節)。SC_X(単精度、非負)を2πで割った
;   小数部をSC_FRACへ書く(l4_mbf_oracle_v10_m9.py _rr_reduce_single_m9)。
;   y=SC_X*IN2PI_SINGLE(away乗算)→n=floor(y)(SC_X>=0よりy>=0なので
;   0方向切り捨て=floor)→frac=-(n-y)=y-n。破壊: 全レジスタ。
; ---------------------------------------------------------------------
SC_RR_REDUCE:
    LD HL,SC_X
    CALL SC_SET_OPA
    LD HL,SC_IN2PI_SINGLE
    CALL SC_SET_OPB
    CALL SIN_MUL_ADDR      ; MBF_RES = y (away丸め乗算)
    LD DE,SC_Y
    CALL SC_GET_RES
    LD HL,SC_Y
    CALL SC_SET_OPA
    CALL SIN_TRUNC_ADDR         ; MBF_RES = floor(y) = n (y>=0のため0方向切り捨て=floor)
    LD DE,SC_N
    CALL SC_GET_RES
    LD HL,SC_N
    CALL SC_SET_OPA
    LD HL,SC_Y
    CALL SC_SET_OPB
    CALL SIN_SUB_ADDR       ; MBF_RES = n - y
    LD HL,MBF_RES
    CALL SC_SET_OPA
    CALL SIN_NEG_ADDR        ; MBF_RES = -(n-y) = y-n = frac
    LD DE,SC_FRAC
    CALL SC_GET_RES
    RET

; ---------------------------------------------------------------------
; SC_POLY_STEP — Horner多項式評価の1段(l4_mbf_oracle_v10_m9.py
;   _poly_eval_away): acc=away_mul(acc,SC_X2); acc=away_add(c,acc)。
;   入力: HL=係数cへのポインタ(4byte)、SC_ACC/SC_X2。
;   出力: SC_ACC更新。破壊: 全レジスタ。
; ---------------------------------------------------------------------
SC_POLY_STEP:
    PUSH HL
    LD HL,SC_ACC
    CALL SC_SET_OPA
    LD HL,SC_X2
    CALL SC_SET_OPB
    CALL SIN_MUL_ADDR        ; MBF_RES = acc*x2
    LD DE,SC_ACC
    CALL SC_GET_RES
    POP HL                       ; HL = 係数cへのポインタ
    CALL SC_SET_OPA               ; MBF_OPA = c
    LD HL,SC_ACC
    CALL SC_SET_OPB                ; MBF_OPB = acc
    CALL SIN_ADD_ADDR             ; MBF_RES = c+acc
    LD DE,SC_ACC
    CALL SC_GET_RES
    RET

; ---------------------------------------------------------------------
; SC_POLYX_SINCN — l4_mbf_oracle_v10_m9.py _polyx_eval_away(x,SINCN):
;   x2=away_mul(x,x); p=poly_eval_away(x2,SINCN); return away_mul(p,x)。
;   入力: SC_REDUCED。出力: MBF_RES。破壊: 全レジスタ。
; ---------------------------------------------------------------------
SC_POLYX_SINCN:
    LD HL,SC_REDUCED
    CALL SC_SET_OPA
    LD HL,SC_REDUCED
    CALL SC_SET_OPB
    CALL SIN_MUL_ADDR         ; MBF_RES = x2 = reduced^2
    LD DE,SC_X2
    CALL SC_GET_RES
    LD HL,SC_SINCN0
    LD DE,SC_ACC
    CALL SC_COPY4                 ; acc = SINCN[0]
    LD HL,SC_SINCN1
    CALL SC_POLY_STEP
    LD HL,SC_SINCN2
    CALL SC_POLY_STEP
    LD HL,SC_SINCN3
    CALL SC_POLY_STEP
    LD HL,SC_SINCN4
    CALL SC_POLY_STEP
    LD HL,SC_ACC
    CALL SC_SET_OPA
    LD HL,SC_REDUCED
    CALL SC_SET_OPB
    JP SIN_MUL_ADDR             ; MBF_RES = acc*reduced (末尾呼び出し、RETは常駐MBF_MUL側)

; ---------------------------------------------------------------------
; SC_SIN_CORE — l4_mbf_oracle_v10_m9.py _sin_core_m9。
;   入力: SC_FRAC(frac_turns、[0,1))、SC_NEG(outer_neg、0/1)。
;   出力: MBF_RES。破壊: 全レジスタ。
; ---------------------------------------------------------------------
SC_SIN_CORE:
    ; quad = frac_turns*4 (2の整数乗、厳密。指数byteに+2するだけ)
    LD A,(SC_FRAC+3)
    OR A
    JP Z,_sc_quad_zero
    ADD A,2
    LD (SC_QUAD+3),A
    JP _sc_quad_rest
_sc_quad_zero:
    XOR A
    LD (SC_QUAD+3),A
_sc_quad_rest:
    LD A,(SC_FRAC)
    LD (SC_QUAD),A
    LD A,(SC_FRAC+1)
    LD (SC_QUAD+1),A
    LD A,(SC_FRAC+2)
    LD (SC_QUAD+2),A

    ; q_num = floor(quad) (quad>=0のため0方向切り捨て=floor)
    LD HL,SC_QUAD
    CALL SC_SET_OPA
    CALL SIN_TRUNC_ADDR
    LD DE,SC_QNUM
    CALL SC_GET_RES
    CALL SC_QNUM_TO_Q            ; (SC_Q) = q(0-3)

    ; sub = -(q_num-quad) = quad-q_num (away減算+away符号反転)
    LD HL,SC_QNUM
    CALL SC_SET_OPA
    LD HL,SC_QUAD
    CALL SC_SET_OPB
    CALL SIN_SUB_ADDR
    LD HL,MBF_RES
    CALL SC_SET_OPA
    CALL SIN_NEG_ADDR
    LD DE,SC_SUB
    CALL SC_GET_RES

    ; q in (1,3)なら sub = 1-sub
    LD A,(SC_Q)
    CP 1
    JP Z,_sc_sub_flip
    CP 3
    JP NZ,_sc_sub_done
_sc_sub_flip:
    LD HL,SC_ONE_SINGLE
    CALL SC_SET_OPA
    LD HL,SC_SUB
    CALL SC_SET_OPB
    CALL SIN_SUB_ADDR
    LD DE,SC_SUB
    CALL SC_GET_RES
_sc_sub_done:

    ; reduced_sp = sub/4 (2の整数乗、厳密に指数byteから-2するだけだが、
    ; tools/l4_mbf_oracle_v2.py _encode_mbf_away同様、結果の指数byteが
    ; 1未満(=表現できないほど小さい)ならゼロへアンダーフローさせる
    ; ——単純にSUB 2するだけだと8bit減算がラップし、指数byte0xFF
    ; (=オーバーフロー値と紛らわしい巨大な指数)を作ってしまい、後段の
    ; MBF_MUL(SC_POLYX_SINCN・微小角分岐のTWO_PI乗算)が実際に
    ; オーバーフローする不具合を2026-09-20 tools/l4_sincos_bank_conform.py
    ; (`sin(1000000)`・`sin(-1000000)`)で検出し修正した(象限内の位置subが
    ; たまたま象限境界の近くに来た大きい引数で、SC_SUB指数byteが1か2に
    ; なるケースで踏む)。
    LD A,(SC_SUB+3)
    OR A
    JP Z,_sc_reduced_zero
    CP 3
    JP C,_sc_reduced_zero     ; 元の指数byteが1か2(=/4するとアンダーフロー)
    SUB 2
    LD (SC_REDUCED+3),A
    JP _sc_reduced_rest
_sc_reduced_zero:
    XOR A
    LD (SC_REDUCED+3),A
    LD (SC_REDUCED),A
    LD (SC_REDUCED+1),A
    LD (SC_REDUCED+2),A
    JP _sc_reduced_done
_sc_reduced_rest:
    LD A,(SC_SUB)
    LD (SC_REDUCED),A
    LD A,(SC_SUB+1)
    LD (SC_REDUCED+1),A
    LD A,(SC_SUB+2)
    LD (SC_REDUCED+2),A
_sc_reduced_done:

    ; reduced_sp.exp!=0 かつ exp<0o164(116)なら微小角近似(*2π)、
    ; それ以外はHorner多項式評価(SINCN)。
    LD A,(SC_REDUCED+3)
    OR A
    JP Z,_sc_use_poly
    CP 116
    JP NC,_sc_use_poly
    LD HL,SC_REDUCED
    CALL SC_SET_OPA
    LD HL,SC_TWO_PI
    CALL SC_SET_OPB
    CALL SIN_MUL_ADDR
    LD DE,SC_RESULT
    CALL SC_GET_RES
    JP _sc_after_poly
_sc_use_poly:
    CALL SC_POLYX_SINCN
    LD DE,SC_RESULT
    CALL SC_GET_RES
_sc_after_poly:

    ; q in (2,3)なら符号反転
    LD A,(SC_Q)
    CP 2
    JP Z,_sc_negate_q
    CP 3
    JP NZ,_sc_skip_qneg
_sc_negate_q:
    LD HL,SC_RESULT
    CALL SC_SET_OPA
    CALL SIN_NEG_ADDR
    LD DE,SC_RESULT
    CALL SC_GET_RES
_sc_skip_qneg:

    ; outer_negなら符号反転
    LD A,(SC_NEG)
    OR A
    JP Z,_sc_skip_outerneg
    LD HL,SC_RESULT
    CALL SC_SET_OPA
    CALL SIN_NEG_ADDR
    LD DE,SC_RESULT
    CALL SC_GET_RES
_sc_skip_outerneg:
    LD HL,SC_RESULT
    LD DE,MBF_RES
    CALL SC_COPY4
    RET

; ---------------------------------------------------------------------
; SC_SIN_IMPL — l4_mbf_oracle_v10_m9.py sin_impl。
;   入力: MBF_OPA=x(単精度)。出力: MBF_RES=sin(x)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
SC_SIN_IMPL:
    ; SIN10: exp!=0 かつ exp<0o167(119)なら x=sin(x) として即リターン
    LD A,(MBF_OPA+3)
    OR A
    JP Z,_sc_sin_notiny
    CP 119
    JP NC,_sc_sin_notiny
    LD HL,MBF_OPA
    LD DE,MBF_RES
    CALL SC_COPY4
    RET
_sc_sin_notiny:
    LD A,(MBF_OPA+2)
    AND 0x80
    JP Z,_sc_sin_pos
    LD A,1
    LD (SC_NEG),A
    CALL SIN_NEG_ADDR          ; MBF_RES = -x = |x| (MBF_OPAはまだx)
    LD DE,SC_X
    CALL SC_GET_RES
    JP _sc_sin_have_xx
_sc_sin_pos:
    XOR A
    LD (SC_NEG),A
    LD HL,MBF_OPA
    LD DE,SC_X
    CALL SC_COPY4
_sc_sin_have_xx:
    CALL SC_RR_REDUCE              ; SC_X -> SC_FRAC
    JP SC_SIN_CORE                 ; SC_FRAC・SC_NEG -> MBF_RES、RETで戻る

; ---------------------------------------------------------------------
; SC_COS_IMPL — l4_mbf_oracle_v10_m9.py cos_impl: cos(x)=sin(x+PI2)
;   (加算はxもPI2も単精度なのでaway単精度加算のまま、force_to_singleは
;   恒等——コメントの根拠は本ファイル冒頭のSIN/COS/TAN節を参照)。
;   入力: MBF_OPA=x(単精度)。出力: MBF_RES=cos(x)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
SC_COS_IMPL:
    LD HL,SC_PI2
    CALL SC_SET_OPB                ; MBF_OPA==x(呼び出し元設定済み)、MBF_OPB=PI2
    CALL SIN_ADD_ADDR             ; MBF_RES = x+PI2
    LD DE,SC_TMP_A
    CALL SC_GET_RES
    LD HL,SC_TMP_A
    LD DE,MBF_OPA
    CALL SC_COPY4                    ; MBF_OPA = x+PI2 (SC_SIN_IMPLへの入力として使う)
    JP SC_SIN_IMPL                   ; 末尾呼び出し、RETは向こうで行う

; ---------------------------------------------------------------------
; SC_TAN_IMPL — l4_mbf_oracle_v10_m9.py tan_impl: tan(x)=away_div(sin(x),cos(x))。
;   入力: MBF_OPA=x(単精度)。出力: MBF_RES=tan(x)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
SC_TAN_IMPL:
    LD HL,MBF_OPA
    LD DE,SC_TAN_X
    CALL SC_COPY4                    ; xを退避(SIN/COS_IMPLがMBF_OPAを上書きするため)
    CALL SC_SIN_IMPL                 ; MBF_RES = sin(x)
    LD DE,SC_SINVAL
    CALL SC_GET_RES
    LD HL,SC_TAN_X
    LD DE,MBF_OPA
    CALL SC_COPY4                    ; MBF_OPA = x (COS_IMPLの前提を再度満たす)
    CALL SC_COS_IMPL                 ; MBF_RES = cos(x)
    LD DE,SC_COSVAL
    CALL SC_GET_RES
    LD HL,SC_SINVAL
    CALL SC_SET_OPA
    LD HL,SC_COSVAL
    CALL SC_SET_OPB
    JP SIN_DIV_ADDR                ; MBF_RES = sin/cos (away丸め除算)、
                                       ; MBF_STATUS=2なら0除算(呼び出し元
                                       ; interp.asm FTNF_DO_TANが判定する)。
                                       ; 末尾呼び出し、RETは常駐MBF_DIV側。

; =======================================================================
; ATN/EXP/LOG(単精度、2026-09-20追記) — docs/spec/l4-program.md 第4.16b節
; (`l4-s6h`で確定したround-half-away丸め)。手順・係数・分岐条件は
; tools/l4_mbf_oracle_v10_m9.py の atn_impl/exp_impl/log_impl(M9、
; SIN/COS/TANと同じ丸めをATN/EXP/LOGへ適用した候補)をそのままZ80へ
; 移した。係数の出所はtools/l4_mbf_oracle_v3.pyのATNC1・ATNC2・EXPCN・
; LOGP・LOGQ・LOG2E・LN2・TAN_PI12・SQRT3・PI6(コメントにGW-BASIC MIT
; 公開ソースMATH1.ASM/MATH2.ASMの行番号を明記——係数の当てはめは行って
; いない)。PI2・ONE_S(=1.0)は既にSIN/COS用に定義済みのSC_PI2・
; SC_ONE_SINGLEをそのまま再利用する(同じ8進DB列、二重定義しない)。
;
; 演算は全てSIN/COS/TANと同じ常駐部(mbf_single.asm)のMBF_ADD/MBF_SUB/
; MBF_MUL/MBF_DIV/MBF_NEG/MBF_CMP(away丸め、l4-s7a・l4-s7b)を
; EXT_BANK_CALL越しにCALLする(docs/spec/ext-rom-bank.md 第2節 制約3
; 準拠、SIN/COS/TANと同じ手法)。floor(EXPのfloor(y))はFTNF_DO_INT
; (interp.asm)と同じ「TRUNC_TO_SINGLE(0方向切り捨て)+負かつ端数
; ありなら-1.0」の手順をAEL_FLOORとして持つ(EXPのyは負にもなりうる
; ため、SIN/COS/TANのSC_RR_REDUCEのように「非負だから0方向切り捨て=
; floor」とは言えない)。EXPのny(floor(y)の整数化、2^ny構成用)は、
; 常駐部のMBF_ROUND_TO_INT16(run.asm)を呼ぶ案だとその番地がATN/EXP/LOG
; 追加後の総バイト数増でちょうど窓(0x6000以上)へ入ってしまうと分かった
; ため、AEL_EXP_NY_TO_INT16として自己完結に実装した(floor済みの値は
; 端数を持たない厳密な整数なので丸め処理は不要、MBF_UNPACK_A相当の
; 展開だけをやり直す)。LOGのe_raw→単精度化はMBF_INT_TO_SINGLE(既存、
; SQR等では未使用だったが元々EXT_BANK_CALLABLE_RESIDENT_LABELSに
; 登録済み)を使う。
;
; 誤り(第7.1節・第4.16節「実装メモ」): LOG(0)・LOG(負)はIllegal function
; call(5)——interp.asm FTNF_DO_LOGがEXT_BANK_CALLする前にMBF_OPAの符号・
; ゼロを判定する(FTNF_DO_SQRの負数判定と同じ手法、バンク0側はx>0のみを
; 前提にできる)。EXPのオーバーフロー(y.exp>=0o210、またはexp2>255)は
; Overflow(6)——バンク0側がMBF_STATUSを直接1に立てて戻り、interp.asm
; FTNF_DO_EXPは既存のVAL_CHECK_MBF_STATUS(MBF_STATUS!=0ならOverflow)を
; そのまま使う(TAN用の専用ラッパーのような新設は不要、EXPの誤りは
; Overflowだけのため)。ATNは有限入力に対し誤りを返さない
; (l4_mbf_oracle_v10_m9.py atn_implはGwErrorを投げない)。
; =======================================================================

; 常駐部アドレス(build_main_rom.pyが実測アドレスへテキスト置換する、
; SIN_ADD_ADDR等と同じ手法。プレースホルダの値0x1787は
; make_ext_rom_banks.pyのGENERIC_ADDR_PLACEHOLDERと一致させる必要があり、
; 実際の値ではない)。
AEL_ADD_ADDR EQU 0x1787   ; MBF_ADD
AEL_SUB_ADDR EQU 0x1787   ; MBF_SUB
AEL_MUL_ADDR EQU 0x1787   ; MBF_MUL
AEL_DIV_ADDR EQU 0x1787   ; MBF_DIV
AEL_NEG_ADDR EQU 0x1787   ; MBF_NEG
AEL_CMP_ADDR EQU 0x1787   ; MBF_CMP
AEL_TRUNC_ADDR EQU 0x1787   ; TRUNC_TO_SINGLE
AEL_ITOS_ADDR EQU 0x1787   ; MBF_INT_TO_SINGLE(LOGのe_raw→単精度)
; EXPのny(floor(y)の整数化、2^ny構成用)は、常駐部のMBF_ROUND_TO_INT16を
; 呼ぶとその番地がちょうど窓(0x6000以上)へ入ってしまう(ATN/EXP/LOG追加で
; N88.ROM総バイト数が伸びたため、docs/spec/ext-rom-bank.md第2節制約3(a)
; 違反になる)ことが分かったため、下記AEL_EXP_NY_TO_INT16として自己完結に
; 実装する(常駐呼び出しにしない)。

; 作業域(単精度4byte、SC_*(0xC320-0xC35D)と重ならない0xC380以降を使う
; (同ファイルのSC_*コメントにある「衝突しない空きを選ぶ」方針の踏襲)。
; ATN・EXP・LOGは呼び出し元(interp.asm)が同時に2つ以上を実行することは
; ない(BASICインタプリタは単一スレッド)ため、関数間で作業域を再利用
; していない——判読性を優先し、各関数専用の番地を割り当てる。
AEL_ATN_X      EQU 0xC380   ; xx(範囲縮約後の作業値、poly_eval/polyx_evalの入力にもなる)
AEL_ATN_XPS    EQU 0xC384   ; x+sqrt(3)
AEL_ATN_NUM    EQU 0xC388   ; poly_eval(xx, ATNC1) = x*sqrt(3)-1相当
AEL_ATN_RESULT EQU 0xC38C   ; 結果(PI6加算・PI2減算・outer_negの前後で共有)
AEL_ATN_NEG    EQU 0xC390   ; outer_neg(0/1、1byte)
AEL_ATN_PI6    EQU 0xC391   ; need_pi6(0/1、1byte)
AEL_ATN_PI2    EQU 0xC392   ; need_pi2(0/1、1byte)

AEL_EXP_Y      EQU 0xC3A0   ; y = x*LOG2E
AEL_EXP_NY     EQU 0xC3A4   ; ny_single = floor(y)(単精度のまま、厳密な整数値)
AEL_EXP_FRAC   EQU 0xC3A8   ; frac = y - ny_single
AEL_EXP_POLY   EQU 0xC3AC   ; poly_eval(frac, EXPCN)
AEL_EXP_POW2   EQU 0xC3B0   ; 2^ny(単精度、仮数0=1.xxxxの意味で厳密)

AEL_LOG_M      EQU 0xC3C0   ; xの仮数はそのまま・指数だけ128に固定した値([0.5,1))
AEL_LOG_P      EQU 0xC3C4   ; poly_eval(m, LOGP)
AEL_LOG_Q      EQU 0xC3C8   ; poly_eval(m, LOGQ)
AEL_LOG_PQ     EQU 0xC3CC   ; P/Q
AEL_LOG_EFLOAT EQU 0xC3D0   ; float(e_raw)(e_raw=xの指数バイト-128)
AEL_LOG_LOG2X  EQU 0xC3D4   ; e_float + P/Q = log2(x)

; Horner多項式評価(poly_eval、_polyx_evalではなくvariableをそのまま
; 使う側)の共有作業域。ATN(ATNC2はx^2側で使うため事前にAEL_POLY_VARへ
; x^2を書く)・EXP(EXPCN)・LOG(LOGP・LOGQ)のいずれも実行順は逐次
; (呼び出し元が単一スレッド)のため共有して構わない。
AEL_POLY_VAR   EQU 0xC3E0   ; Hornerの掛け算対象(x、または_polyx_eval由来のx^2)
AEL_POLY_ACC   EQU 0xC3E4   ; Hornerのアキュムレータ
AEL_TMP_SHIFT  EQU 0xC3E8   ; AEL_EXP_NY_TO_INT16の作業用シフトカウンタ(1byte)

; 定数(単精度4byte)。出所は各定数のコメントを参照——GW-BASIC MIT公開
; ソースMATH1.ASM/MATH2.ASMのインライン即値、8進DB列を16進へ変換した
; だけで係数の当てはめは行っていない(tools/l4_mbf_oracle_v3.pyの
; LOG2E・LN2・TAN_PI12・SQRT3・PI6・EXPCN・ATNC1・ATNC2・LOGP・LOGQ
; そのもの)。PI2・ONE_S(1.0)はSC_PI2・SC_ONE_SINGLEを再利用する。
AEL_LOG2E:
    DB 0x3B,0xAA,0x38,0x81   ; log2(e)(MATH1.ASM 3029-3030)
AEL_LN2:
    DB 0x18,0x72,0x31,0x80   ; ln(2)(MATH2.ASM 1047-1048 MLLN2)
AEL_TAN_PI12:
    DB 0xA2,0x30,0x09,0x7F   ; tan(π/12)(MATH1.ASM 1109-1110)
AEL_SQRT3:
    DB 0xD7,0xB3,0x5D,0x81   ; √3(MATH1.ASM 1117-1118)
AEL_PI6:
    DB 0x92,0x0A,0x06,0x80   ; π/6(MATH1.ASM 1141-1142、ATN200)

AEL_EXPCN0:
    DB 0x7C,0x88,0x59,0x74   ; MATH1.ASM 802-830($EXPCN、Hart #1302)、7係数
AEL_EXPCN1:
    DB 0xE0,0x97,0x26,0x77
AEL_EXPCN2:
    DB 0xC4,0x1D,0x1E,0x7A
AEL_EXPCN3:
    DB 0x5E,0x50,0x63,0x7C
AEL_EXPCN4:
    DB 0x1A,0xFE,0x75,0x7E
AEL_EXPCN5:
    DB 0x18,0x72,0x31,0x80
AEL_EXPCN6:
    DB 0x00,0x00,0x00,0x81

AEL_ATNC1_0:
    DB 0xD7,0xB3,0x5D,0x81   ; MATH1.ASM 857-866(x*sqrt(3)-1の分子生成用)、2係数
AEL_ATNC1_1:
    DB 0x00,0x00,0x80,0x81

AEL_ATNC2_0:
    DB 0x62,0x35,0x83,0x7E   ; MATH1.ASM 867-884(Hart #4940)、4係数
AEL_ATNC2_1:
    DB 0x50,0x24,0x4C,0x7E
AEL_ATNC2_2:
    DB 0x79,0xA9,0xAA,0x7F
AEL_ATNC2_3:
    DB 0x00,0x00,0x00,0x81

AEL_LOGP0:
    DB 0x9A,0xF7,0x19,0x83   ; MATH1.ASM 631-647(Hart #2524、P(x))、4係数
AEL_LOGP1:
    DB 0x24,0x63,0x43,0x83
AEL_LOGP2:
    DB 0x75,0xCD,0x8D,0x84
AEL_LOGP3:
    DB 0xA9,0x7F,0x83,0x82

AEL_LOGQ0:
    DB 0x00,0x00,0x00,0x81   ; MATH1.ASM 648-664(Hart #2524、Q(x))、4係数
AEL_LOGQ1:
    DB 0xE2,0xB0,0x4D,0x83
AEL_LOGQ2:
    DB 0x0A,0x72,0x11,0x83
AEL_LOGQ3:
    DB 0xF4,0x04,0x35,0x7F

; ---------------------------------------------------------------------
; AEL_FLOOR — MBF_OPA(単精度、符号は問わない)の床(floor)をMBF_RESへ
;   書く。interp.asm FTNF_DO_INT(第4.15節E11)と同じ「TRUNC_TO_SINGLE
;   (0方向切り捨て)+負かつ端数ありなら-1.0」の手順(SC_RR_REDUCEの
;   ような「非負だから0方向切り捨て=floor」という単純化はできない、
;   EXPのyは負にもなりうるため)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
; TRUNC_HADFRAC/TRUNC_SIGN(mbf_single.asmのRAM番地、同じ値のEQUをここに
; も持つ——bank0.asmはmbf_single.asmをINCLUDEしないため、MBF_DOPA_RAM等
; 既存のRAM番地EQUと同じ「密結合はコメントで明示」方針の踏襲)。
AEL_TRUNC_HADFRAC EQU 0xC0F0
AEL_TRUNC_SIGN    EQU 0xC0F1

AEL_FLOOR:
    CALL AEL_TRUNC_ADDR         ; MBF_RES = trunc(MBF_OPA)、TRUNC_HADFRAC/TRUNC_SIGN設定
    LD A,(AEL_TRUNC_HADFRAC)
    OR A
    RET Z
    LD A,(AEL_TRUNC_SIGN)
    OR A
    RET Z
    LD HL,MBF_RES
    CALL SC_SET_OPA               ; MBF_OPA = trunc(y)
    LD HL,SC_ONE_SINGLE
    CALL SC_SET_OPB
    JP AEL_SUB_ADDR               ; MBF_RES = trunc(y)-1.0 = floor(y)(末尾呼び出し)

; ---------------------------------------------------------------------
; AEL_POLY_STEP — Horner多項式評価の1段(l4_mbf_oracle_v10_m9.py
;   _poly_eval_awayの1反復): acc=away_mul(acc,AEL_POLY_VAR);
;   acc=away_add(c,acc)。入力: HL=係数cへのポインタ(4byte)、
;   AEL_POLY_ACC/AEL_POLY_VAR。出力: AEL_POLY_ACC更新。破壊: 全レジスタ。
;   SC_POLY_STEP(SINCN専用、変数はSC_X2固定)と同型だが、変数を
;   AEL_POLY_VARへ一般化しATN/EXP/LOGで共有する。
; ---------------------------------------------------------------------
AEL_POLY_STEP:
    PUSH HL
    LD HL,AEL_POLY_ACC
    CALL SC_SET_OPA
    LD HL,AEL_POLY_VAR
    CALL SC_SET_OPB
    CALL AEL_MUL_ADDR            ; MBF_RES = acc*var
    LD DE,AEL_POLY_ACC
    CALL SC_GET_RES
    POP HL                        ; HL = 係数cへのポインタ
    CALL SC_SET_OPA                ; MBF_OPA = c
    LD HL,AEL_POLY_ACC
    CALL SC_SET_OPB                 ; MBF_OPB = acc
    CALL AEL_ADD_ADDR              ; MBF_RES = c+acc
    LD DE,AEL_POLY_ACC
    CALL SC_GET_RES
    RET

; ---------------------------------------------------------------------
; AEL_EXP_NY_TO_INT16 — AEL_EXP_NY(単精度、floor(y)で得た端数の無い
;   厳密な整数値、符号は問わない)を符号付き16bit(DE)へ変換する。
;   常駐部のMBF_ROUND_TO_INT16(run.asm)と同じ「value=M24*2^(exp-152)、
;   shift=152-exp」の式(TRUNC_TO_SINGLEの152定数と同じ導出)を使うが、
;   端数が無い(floor済み)ことが構造上保証されているため丸め処理
;   (端数ビットの判定)は不要——MBF_UNPACK_A相当の展開だけを
;   自己完結にやり直す(bank0.asm 冒頭コメント「AEL_ROUND_ADDR」参照、
;   常駐呼び出しにすると窓の外に収まらなくなったための判断)。
;   |ny|は呼び出し元(AEL_EXP_IMPL)のy.exp<0o210(136)判定により
;   256未満に収まる(shift>=16、24bitマンティッサの上位バイトは
;   シフトの末に必ず0になり16bitに収まる)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
AEL_EXP_NY_TO_INT16:
    LD A,(AEL_EXP_NY+3)
    OR A
    JP NZ,_aeni_nonzero
    LD DE,0
    RET
_aeni_nonzero:
    LD C,A                       ; C = 指数バイト
    LD A,(AEL_EXP_NY+2)
    AND 0x7F
    OR 0x80
    LD B,A                       ; B:D:E = 24bit仮数(implicit先頭1含む、MSB=B)
    LD A,(AEL_EXP_NY+1)
    LD D,A
    LD A,(AEL_EXP_NY)
    LD E,A
    LD A,152
    SUB C
    LD (AEL_TMP_SHIFT),A
_aeni_shift_loop:
    LD A,(AEL_TMP_SHIFT)
    OR A
    JP Z,_aeni_shift_done
    SRL B
    RR D
    RR E
    DEC A
    LD (AEL_TMP_SHIFT),A
    JP _aeni_shift_loop
_aeni_shift_done:
    ; (D:E) = 符号なし整数値(16bit、Bは0のはず)
    LD A,(AEL_EXP_NY+2)
    AND 0x80
    JP Z,_aeni_pos
    XOR A
    SUB E
    LD E,A
    LD A,0
    SBC A,D
    LD D,A
_aeni_pos:
    RET                            ; DE = 結果(符号付き16bit)

; ---------------------------------------------------------------------
; AEL_ATN_IMPL — l4_mbf_oracle_v10_m9.py atn_impl。
;   入力: MBF_OPA=x(単精度)。出力: MBF_RES=atn(x)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
AEL_ATN_IMPL:
    ; neg = x.is_negative(); xx = |x|
    LD A,(MBF_OPA+2)
    AND 0x80
    JP Z,_ael_atn_pos
    LD A,1
    LD (AEL_ATN_NEG),A
    CALL AEL_NEG_ADDR             ; MBF_RES = -x = |x|
    LD DE,AEL_ATN_X
    CALL SC_GET_RES
    JP _ael_atn_have_x
_ael_atn_pos:
    XOR A
    LD (AEL_ATN_NEG),A
    LD HL,MBF_OPA
    LD DE,AEL_ATN_X
    CALL SC_COPY4
_ael_atn_have_x:
    ; need_pi2 = xx.exp!=0 かつ xx.exp>=0o201(129)
    LD A,(AEL_ATN_X+3)
    OR A
    JP Z,_ael_atn_no_pi2
    CP 129
    JP C,_ael_atn_no_pi2
    LD A,1
    LD (AEL_ATN_PI2),A
    LD HL,SC_ONE_SINGLE            ; ONE_S(=1.0、SIN/COSと共通)
    CALL SC_SET_OPA
    LD HL,AEL_ATN_X
    CALL SC_SET_OPB
    CALL AEL_DIV_ADDR              ; MBF_RES = 1/xx
    LD DE,AEL_ATN_X
    CALL SC_GET_RES                ; xx = 1/xx
    JP _ael_atn_have_pi2
_ael_atn_no_pi2:
    XOR A
    LD (AEL_ATN_PI2),A
_ael_atn_have_pi2:
    ; need_pi6 = xx.exact() > TAN_PI12.exact() (実値比較、MBF_CMP)
    LD HL,AEL_ATN_X
    CALL SC_SET_OPA
    LD HL,AEL_TAN_PI12
    CALL SC_SET_OPB
    CALL AEL_CMP_ADDR
    LD A,(MBF_OUT_CMP)
    CP 1
    JP NZ,_ael_atn_no_pi6
    LD A,1
    LD (AEL_ATN_PI6),A
    ; xps = xx + sqrt(3)
    LD HL,AEL_ATN_X
    CALL SC_SET_OPA
    LD HL,AEL_SQRT3
    CALL SC_SET_OPB
    CALL AEL_ADD_ADDR
    LD DE,AEL_ATN_XPS
    CALL SC_GET_RES
    ; num = poly_eval(xx, ATNC1) = acc(ATNC1[0]); acc=away_mul(acc,xx); acc=away_add(ATNC1[1],acc)
    LD HL,AEL_ATN_X
    LD DE,AEL_POLY_VAR
    CALL SC_COPY4
    LD HL,AEL_ATNC1_0
    LD DE,AEL_POLY_ACC
    CALL SC_COPY4
    LD HL,AEL_ATNC1_1
    CALL AEL_POLY_STEP
    LD HL,AEL_POLY_ACC
    LD DE,AEL_ATN_NUM
    CALL SC_COPY4
    ; xx = num / xps
    LD HL,AEL_ATN_NUM
    CALL SC_SET_OPA
    LD HL,AEL_ATN_XPS
    CALL SC_SET_OPB
    CALL AEL_DIV_ADDR
    LD DE,AEL_ATN_X
    CALL SC_GET_RES
    JP _ael_atn_after_pi6
_ael_atn_no_pi6:
    XOR A
    LD (AEL_ATN_PI6),A
_ael_atn_after_pi6:
    ; result = polyx_eval(xx, ATNC2): x2=away_mul(xx,xx); p=poly_eval(x2,ATNC2); result=away_mul(p,xx)
    LD HL,AEL_ATN_X
    CALL SC_SET_OPA
    LD HL,AEL_ATN_X
    CALL SC_SET_OPB
    CALL AEL_MUL_ADDR              ; MBF_RES = xx^2
    LD DE,AEL_POLY_VAR
    CALL SC_GET_RES
    LD HL,AEL_ATNC2_0
    LD DE,AEL_POLY_ACC
    CALL SC_COPY4
    LD HL,AEL_ATNC2_1
    CALL AEL_POLY_STEP
    LD HL,AEL_ATNC2_2
    CALL AEL_POLY_STEP
    LD HL,AEL_ATNC2_3
    CALL AEL_POLY_STEP
    LD HL,AEL_POLY_ACC
    CALL SC_SET_OPA
    LD HL,AEL_ATN_X
    CALL SC_SET_OPB
    CALL AEL_MUL_ADDR              ; MBF_RES = p*xx
    LD DE,AEL_ATN_RESULT
    CALL SC_GET_RES
    ; if need_pi6: result = PI6 + result
    LD A,(AEL_ATN_PI6)
    OR A
    JP Z,_ael_atn_skip_pi6add
    LD HL,AEL_PI6
    CALL SC_SET_OPA
    LD HL,AEL_ATN_RESULT
    CALL SC_SET_OPB
    CALL AEL_ADD_ADDR
    LD DE,AEL_ATN_RESULT
    CALL SC_GET_RES
_ael_atn_skip_pi6add:
    ; if need_pi2: result = PI2 - result
    LD A,(AEL_ATN_PI2)
    OR A
    JP Z,_ael_atn_skip_pi2sub
    LD HL,SC_PI2
    CALL SC_SET_OPA
    LD HL,AEL_ATN_RESULT
    CALL SC_SET_OPB
    CALL AEL_SUB_ADDR
    LD DE,AEL_ATN_RESULT
    CALL SC_GET_RES
_ael_atn_skip_pi2sub:
    ; if neg: result = -result
    LD A,(AEL_ATN_NEG)
    OR A
    JP Z,_ael_atn_finish
    LD HL,AEL_ATN_RESULT
    CALL SC_SET_OPA
    CALL AEL_NEG_ADDR
    LD DE,AEL_ATN_RESULT
    CALL SC_GET_RES
_ael_atn_finish:
    LD HL,AEL_ATN_RESULT
    LD DE,MBF_RES
    JP SC_COPY4

; ---------------------------------------------------------------------
; AEL_EXP_IMPL — l4_mbf_oracle_v10_m9.py exp_impl。
;   入力: MBF_OPA=x(単精度)。出力: MBF_RES=exp(x)、
;   MBF_STATUS(0=正常/1=オーバーフロー、interp.asm FTNF_DO_EXPが
;   VAL_CHECK_MBF_STATUSで判定)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
AEL_EXP_IMPL:
    ; y = x*LOG2E (MBF_OPA==x、呼び出し元設定済み)
    LD HL,AEL_LOG2E
    CALL SC_SET_OPB
    CALL AEL_MUL_ADDR
    ; l4_mbf_oracle_v10_m9.py exp_impl: away_binop(x,LOG2E,"*")自体が
    ; 単精度の表現域を超えれば、y.exp>=0o210の判定に届く前にそこで
    ; Overflowを投げる(xが単精度の最大値付近で|x|*log2(e)が単精度の
    ; 指数バイト255を超える場合、l4_atnexplog_bank_conform.pyの
    ; 境界値照合〔最大負〕で実際に踏んだ)。MBF_MULが既に立てた
    ; MBF_STATUSを先に見て、ここで即座に戻る(この後の「y.exp>=136なら
    ; 負→0」分岐は、乗算自体は正常に収まったが値が大きい場合だけの話
    ; ——乗算そのものが表現域を超えた場合と混同しない)。
    LD A,(MBF_STATUS)
    OR A
    RET NZ                          ; MBF_STATUS=1のまま戻る(Overflow)
    LD DE,AEL_EXP_Y
    CALL SC_GET_RES
    ; y.exp!=0 かつ y.exp>=0o210(136) なら: 負→0、正→Overflow
    LD A,(AEL_EXP_Y+3)
    OR A
    JP Z,_ael_exp_check_small
    CP 136
    JP C,_ael_exp_check_small
    LD A,(AEL_EXP_Y+2)
    AND 0x80
    JP Z,_ael_exp_overflow
    XOR A
    LD (MBF_RES),A
    LD (MBF_RES+1),A
    LD (MBF_RES+2),A
    LD (MBF_RES+3),A
    XOR A
    LD (MBF_STATUS),A
    RET
_ael_exp_overflow:
    LD A,1
    LD (MBF_STATUS),A
    RET
_ael_exp_check_small:
    ; y.exp==0 または y.exp<0o150(104) なら 1.0
    LD A,(AEL_EXP_Y+3)
    OR A
    JP Z,_ael_exp_return_one
    CP 104
    JP NC,_ael_exp_body
_ael_exp_return_one:
    LD HL,SC_ONE_SINGLE
    LD DE,MBF_RES
    CALL SC_COPY4
    XOR A
    LD (MBF_STATUS),A
    RET
_ael_exp_body:
    ; ny_single = floor(y)
    LD HL,AEL_EXP_Y
    CALL SC_SET_OPA
    CALL AEL_FLOOR
    LD DE,AEL_EXP_NY
    CALL SC_GET_RES
    ; frac = y - ny_single
    LD HL,AEL_EXP_Y
    CALL SC_SET_OPA
    LD HL,AEL_EXP_NY
    CALL SC_SET_OPB
    CALL AEL_SUB_ADDR
    LD DE,AEL_EXP_FRAC
    CALL SC_GET_RES
    ; poly_result = poly_eval(frac, EXPCN)(7係数、Horner)
    LD HL,AEL_EXP_FRAC
    LD DE,AEL_POLY_VAR
    CALL SC_COPY4
    LD HL,AEL_EXPCN0
    LD DE,AEL_POLY_ACC
    CALL SC_COPY4
    LD HL,AEL_EXPCN1
    CALL AEL_POLY_STEP
    LD HL,AEL_EXPCN2
    CALL AEL_POLY_STEP
    LD HL,AEL_EXPCN3
    CALL AEL_POLY_STEP
    LD HL,AEL_EXPCN4
    CALL AEL_POLY_STEP
    LD HL,AEL_EXPCN5
    CALL AEL_POLY_STEP
    LD HL,AEL_EXPCN6
    CALL AEL_POLY_STEP
    LD HL,AEL_POLY_ACC
    LD DE,AEL_EXP_POLY
    CALL SC_COPY4
    ; ny(整数、DE) = ny_single の整数値(floor済みで端数0なので厳密)
    CALL AEL_EXP_NY_TO_INT16       ; DE = ny(符号付き16bit)、自己完結
                                     ; (AEL_TMP_SHIFT EQUのコメント参照)
    ; exp2 = ny+129
    LD HL,129
    ADD HL,DE
    LD A,H
    OR A
    JP NZ,_ael_exp_check_hi
    LD A,L
    OR A
    JP Z,_ael_exp_underflow         ; exp2==0 -> <1 -> 0
    LD (AEL_EXP_POW2+3),A           ; 1<=exp2<=255
    JP _ael_exp_pow2_ready
_ael_exp_check_hi:
    BIT 7,H
    JP NZ,_ael_exp_underflow        ; exp2<0 -> <1 -> 0
    LD A,1
    LD (MBF_STATUS),A               ; exp2>255 -> Overflow
    RET
_ael_exp_underflow:
    XOR A
    LD (MBF_RES),A
    LD (MBF_RES+1),A
    LD (MBF_RES+2),A
    LD (MBF_RES+3),A
    XOR A
    LD (MBF_STATUS),A
    RET
_ael_exp_pow2_ready:
    XOR A
    LD (AEL_EXP_POW2),A
    LD (AEL_EXP_POW2+1),A
    LD (AEL_EXP_POW2+2),A            ; 仮数0(=1.0xxx)、符号0
    ; result = poly_result * 2^ny
    LD HL,AEL_EXP_POLY
    CALL SC_SET_OPA
    LD HL,AEL_EXP_POW2
    CALL SC_SET_OPB
    JP AEL_MUL_ADDR                  ; MBF_RES = result、MBF_STATUS=0(末尾呼び出し)

; ---------------------------------------------------------------------
; AEL_LOG_IMPL — l4_mbf_oracle_v10_m9.py log_impl。x<=0の判定は
;   呼び出し元(interp.asm FTNF_DO_LOG)がEXT_BANK_CALL前に済ませる
;   (FTNF_DO_SQRの負数判定と同じ手法)ため、ここはx>0のみを前提にする。
;   入力: MBF_OPA=x(単精度、x>0)。出力: MBF_RES=log(x)。破壊: 全レジスタ。
; ---------------------------------------------------------------------
AEL_LOG_IMPL:
    ; x.exact()==1 なら 0.0 (MBF_CMPでSC_ONE_SINGLEと比較)
    LD HL,MBF_OPA
    CALL SC_SET_OPA
    LD HL,SC_ONE_SINGLE
    CALL SC_SET_OPB
    CALL AEL_CMP_ADDR
    LD A,(MBF_OUT_CMP)
    OR A
    JP NZ,_ael_log_notone
    XOR A
    LD (MBF_RES),A
    LD (MBF_RES+1),A
    LD (MBF_RES+2),A
    LD (MBF_RES+3),A
    RET
_ael_log_notone:
    ; e_raw = x.exp-128 (符号付き)、e_float = float(e_raw)
    LD A,(MBF_OPA+3)
    SUB 128
    LD L,A
    LD H,0
    BIT 7,L
    JP Z,_ael_log_eraw_pos
    LD H,0xFF
_ael_log_eraw_pos:
    LD (MBF_IN_INT),HL
    CALL AEL_ITOS_ADDR              ; MBF_RES = float(e_raw)
    LD DE,AEL_LOG_EFLOAT
    CALL SC_GET_RES
    ; m = 仮数はxのまま(byte0-2)、指数だけ128(0x80)に固定
    LD HL,MBF_OPA
    LD DE,AEL_LOG_M
    LD BC,3
    LDIR
    LD A,0x80
    LD (AEL_LOG_M+3),A
    ; p = poly_eval(m, LOGP)(4係数)
    LD HL,AEL_LOG_M
    LD DE,AEL_POLY_VAR
    CALL SC_COPY4
    LD HL,AEL_LOGP0
    LD DE,AEL_POLY_ACC
    CALL SC_COPY4
    LD HL,AEL_LOGP1
    CALL AEL_POLY_STEP
    LD HL,AEL_LOGP2
    CALL AEL_POLY_STEP
    LD HL,AEL_LOGP3
    CALL AEL_POLY_STEP
    LD HL,AEL_POLY_ACC
    LD DE,AEL_LOG_P
    CALL SC_COPY4
    ; q = poly_eval(m, LOGQ)(4係数、AEL_POLY_VAR=mは変わらず共有)
    LD HL,AEL_LOGQ0
    LD DE,AEL_POLY_ACC
    CALL SC_COPY4
    LD HL,AEL_LOGQ1
    CALL AEL_POLY_STEP
    LD HL,AEL_LOGQ2
    CALL AEL_POLY_STEP
    LD HL,AEL_LOGQ3
    CALL AEL_POLY_STEP
    LD HL,AEL_POLY_ACC
    LD DE,AEL_LOG_Q
    CALL SC_COPY4
    ; pq = p/q
    LD HL,AEL_LOG_P
    CALL SC_SET_OPA
    LD HL,AEL_LOG_Q
    CALL SC_SET_OPB
    CALL AEL_DIV_ADDR
    LD DE,AEL_LOG_PQ
    CALL SC_GET_RES
    ; log2x = e_float + pq
    LD HL,AEL_LOG_EFLOAT
    CALL SC_SET_OPA
    LD HL,AEL_LOG_PQ
    CALL SC_SET_OPB
    CALL AEL_ADD_ADDR
    LD DE,AEL_LOG_LOG2X
    CALL SC_GET_RES
    ; result = log2x * LN2
    LD HL,AEL_LOG_LOG2X
    CALL SC_SET_OPA
    LD HL,AEL_LN2
    CALL SC_SET_OPB
    JP AEL_MUL_ADDR                  ; MBF_RES = result(末尾呼び出し)
