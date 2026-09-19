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
