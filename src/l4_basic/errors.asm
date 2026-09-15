; errors.asm — src/l4_basic/make_error_table.py が生成
; 手で編集しない（再実行で再生成する）。
; 出所: docs/spec/l4-basic.md 第6.1節（開発者判断で採用したマニュアルの
; エラーメッセージ一覧。番号に'?'が付く項は除外済み）。
;
; 今回使うのは構文の誤り(SYNTAX_ERROR_MSG、番号2)の文言だけ。
; 他の項目は一覧として持つのみで、この段階では未使用。

ERR_MSG_1:
    DB "NEXT without FOR",0
ERR_MSG_2:
    DB "Syntax error",0
ERR_MSG_3:
    DB "RETURN without GOSUB",0
ERR_MSG_4:
    DB "Out of DATA",0
ERR_MSG_5:
    DB "Illegal function call",0
ERR_MSG_6:
    DB "Overflow",0
ERR_MSG_7:
    DB "Out of memory",0
ERR_MSG_8:
    DB "Undefined line number",0
ERR_MSG_9:
    DB "Subscript out of range",0
ERR_MSG_10:
    DB "Duplicate Definition",0
ERR_MSG_11:
    DB "Division by zero",0
ERR_MSG_12:
    DB "Illegal direct",0
ERR_MSG_13:
    DB "Type mismatch",0
ERR_MSG_14:
    DB "Out of string space",0
ERR_MSG_15:
    DB "String too long",0
ERR_MSG_16:
    DB "String formula too complex",0
ERR_MSG_17:
    DB "Can't continue",0
ERR_MSG_18:
    DB "Undefined user function",0
ERR_MSG_19:
    DB "No RESUME",0
ERR_MSG_20:
    DB "RESUME without error",0
ERR_MSG_21:
    DB "Unprintable error",0
ERR_MSG_22:
    DB "Missing operand",0
ERR_MSG_23:
    DB "Line buffer overflow",0
ERR_MSG_26:
    DB "FOR without NEXT",0
ERR_MSG_27:
    DB "Tape read ERROR",0
ERR_MSG_29:
    DB "WHILE without WEND",0
ERR_MSG_30:
    DB "WEND without WHILE",0
ERR_MSG_31:
    DB "Duplicate label",0
ERR_MSG_32:
    DB "Undefined label",0
ERR_MSG_33:
    DB "Feature not available",0
ERR_MSG_50:
    DB "FIELD overflow",0
ERR_MSG_51:
    DB "Internal error",0
ERR_MSG_52:
    DB "Bad file number",0
ERR_MSG_53:
    DB "File not found",0
ERR_MSG_54:
    DB "File already open",0
ERR_MSG_55:
    DB "Input past end",0
ERR_MSG_56:
    DB "Bad file name",0
ERR_MSG_57:
    DB "Direct statement in file",0
ERR_MSG_58:
    DB "Sequential after PUT",0
ERR_MSG_59:
    DB "Sequential I/O only",0
ERR_MSG_61:
    DB "File write protected",0
ERR_MSG_62:
    DB "Disk offline",0
ERR_MSG_64:
    DB "Disk I/O error",0
ERR_MSG_65:
    DB "File already exists",0
ERR_MSG_68:
    DB "Disk full",0
ERR_MSG_69:
    DB "Bad allocation table",0
ERR_MSG_70:
    DB "Bad drive number",0
ERR_MSG_71:
    DB "Bad track/sector",0
ERR_MSG_72:
    DB "Deleted record",0
ERR_MSG_73:
    DB "Rename across disks",0

; 構文の誤り（番号2）を直接指す独立ラベル。interp.asmが参照する。
SYNTAX_ERROR_MSG:
    DB "Syntax error",0
