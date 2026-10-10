#!/usr/bin/env python3
"""動的本文・混在ヒープ・ページ・SAVEを実機相当の自作ROMで検査する。"""
from pathlib import Path
import argparse
import re
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
import build_main_rom as build
import memmap
from make_m6fj_disk import build as blank, offsets

FRONT = REPO/'tools/harness/frontend/q88measure'
CORE = next((REPO.parent/'vendor/quasi88-libretro').glob('quasi88_libretro.*'))


def disk_with_program(lines):
    """既存conform_saveと同じB0形式に、自己作成ASCIIファイルを置く。"""
    image = bytearray(blank('B0'))
    positions = offsets(image)
    data = ('\r\n'.join(lines)+'\r\n').encode('ascii')+b'\x1a'
    count = (len(data)+255)//256
    units = list(range(10, 10+(count+7)//8))
    fat = bytearray(image[positions[(18,1,14)]:positions[(18,1,14)]+256])
    for i, unit in enumerate(units):
        fat[unit] = units[i+1] if i+1 < len(units) else 0xC0+(count-1)%8+1
    pos = positions[(18,1,1)]
    image[pos:pos+16] = b'seed'.ljust(9,b' ')+bytes((0,units[0]))+b'\xff'*5
    for sector in (14,15,16):
        pos=positions[(18,1,sector)];image[pos:pos+256]=fat
    for i in range(count):
        linear=units[i//8]*8+i%8
        pos=positions[(linear//32,(linear//16)%2,linear%16+1)]
        image[pos:pos+256]=data[i*256:(i+1)*256].ljust(256,b'\0')
    return bytes(image)


def file_data(image, name, padding=False):
    positions=offsets(image)
    entries=b''.join(image[positions[(18,1,s)]:positions[(18,1,s)]+256] for s in range(1,14))
    entry=next(entries[i:i+16] for i in range(0,len(entries),16)
               if entries[i:i+9].upper()==name.upper().encode().ljust(9,b' '))
    fat=image[positions[(18,1,14)]:positions[(18,1,14)]+256]
    unit=entry[10];data=bytearray();seen=set()
    while True:
        assert unit not in seen and unit<160, 'SAVE FAT鎖'
        seen.add(unit);nxt=fat[unit]
        count=nxt-0xC0 if 0xC1<=nxt<=0xC8 else 8
        for s in range(count):
            linear=unit*8+s
            pos=positions[(linear//32,(linear//16)%2,linear%16+1)]
            data.extend(image[pos:pos+256])
        if 0xC1<=nxt<=0xC8:
            return bytes(data) if padding else bytes(data).split(b'\x1a',1)[0]+b'\x1a'
        unit=nxt


class Suite:
    def __init__(self, work):
        self.work=work;self.rom=work/'rom';self.results=[]
        subprocess.run(['make','-s','-C',str(FRONT.parent)],check=True)
        with (work/'build.log').open('w') as log:
            subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(self.rom)],
                           stdout=log,stderr=log,check=True)
        # LISTの全出力を、既存のメモリ記録から読み取る。スクロールのコピーは除外する。
        aw=work/'asm';aw.mkdir()
        code,asm=build.assemble(build.build_combined_asm(aw,0,False,
                         enable_main_sub_read=True,enable_disk_read_retry=True,
                         enable_disk_read_chr=True,enable_main_sub_boot=False),aw)
        start=asm.labels['_pc_no_capture'];end=asm.labels['NEWLINE']
        self.print_pc=start+code[start:end].index(bytes((0x77,)))

    def run(self, tag, commands, disk=None, trace_at=None, trace_range='F3C8-FF7F', extra=400):
        path=self.work/tag;path.mkdir()
        args=[str(FRONT),'--core',str(CORE),'--rom-dir',str(self.rom)]
        if disk:
            image=path/'disk.d88';image.write_bytes(disk)
            args+=['--disk',str(image),'--save-to-disk-image']
        at=300
        for command,pause in commands:
            args+=['--type-at',str(at),'--type',command+'\\n']
            at+=(len(command)+1)*8+pause
        final=at+extra
        dump=path/'screen.bin'
        args+=['--frames',str(final),'--vram-dump',str(dump),'--vram-dump-at',str(final-50)]
        if trace_at is not None:
            args+=['--mem-write-log',str(path/'writes.tsv'),'--mem-write-range',trace_range,
                   '--mem-write-from-frame',str(trace_at)]
        with (path/'stdout').open('w') as out,(path/'stderr').open('w') as err:
            subprocess.run(args,stdout=out,stderr=err,check=True,stdin=subprocess.DEVNULL,timeout=180)
        screen=dump.read_bytes()
        text='\n'.join(screen[i*120:i*120+80].decode('ascii',errors='replace').rstrip() for i in range(25))
        (path/'screen.txt').write_text(text)
        text=text.lower()
        return path,text

    def ok(self, label):
        self.results.append(label);print('OK '+label,flush=True)

    def large(self):
        lines=[f'{i*10} REM '+('X'*24) for i in range(1,300)]+['3000 PRINT "MDYN300":END']
        assert sum(3+len(line.split(' ',1)[1]) for line in lines)>8192
        commands=[('LOAD "1:seed"',80000),('CLS:LIST',10000),('RUN',1000),
                  ('SAVE "1:round",A',50000),('NEW',200),('LOAD "1:round"',80000),('CLS:RUN',1000)]
        # LOAD終了後のLISTを全行記録し、画面の最後20行だけで件数を判定しない。
        trace=300+(len(commands[0][0])+1)*8+commands[0][1]
        path,text=self.run('large-roundtrip',commands,disk_with_program(lines),trace)
        stream=[];row=[]
        for line in (path/'writes.tsv').read_text().splitlines():
            values=line.split()
            if len(values)!=5 or not re.fullmatch('[0-9A-Fa-f]{4}',values[2]) or int(values[2],16)!=self.print_pc:
                continue
            addr=int(values[3],16);value=int(values[4],16)
            col=(addr-0xF3C8)%120
            if col==0 and row:
                stream.append(bytes(row).decode('ascii'));row=[]
            row.append(value)
        if row:stream.append(bytes(row).decode('ascii'))
        listed=[line for line in stream if re.match(r'^\d+ (REM |PRINT )',line)]
        assert listed==lines, f'LIST件数/本文: {len(listed)}/300 (PC={self.print_pc:04X})'
        assert 'mdyn300' in text and 'error' not in text.lower(), text
        saved=file_data((path/'disk.d88').read_bytes(),'ROUND')
        assert saved==('\r\n'.join(lines)+'\r\n').encode()+b'\x1a', 'SAVE本文/全300行'
        self.ok('本文300行・9KB超、LIST全行・RUN・SAVE ,A→NEW→LOAD往復')

    def wide_capture(self):
        # 本文は短くてもLISTの行番号/CRLFで12KBを超える。割当表も6単位を超える。
        lines=[f'{i*10} REM' for i in range(1,1300)]+['13000 PRINT "WIDEOK":END']
        data=('\r\n'.join(lines)+'\r\n').encode()+b'\x1a'
        assert 12288<len(data)<16384
        commands=[('LOAD "1:seed"',100000),('SAVE "1:wide",A',50000),('NEW',200),
                  ('LOAD "1:wide"',100000),('CLS:RUN',2000)]
        path,text=self.run('capture-over-12kb',commands,disk_with_program(lines))
        assert 'wideok' in text and 'error' not in text,text
        assert file_data((path/'disk.d88').read_bytes(),'wide')==data, '12KB超SAVE全1300行'
        self.ok('捕捉12KB超・7単位以上のSAVE割当、1300行SAVE→LOAD→RUN')

    def capture_edge(self):
        lines=[f'{i*10} REM '+('X'*24) for i in range(1,374)]+['3740 PRINT "EDGEOK":END']
        data=('\r\n'.join(lines)+'\r\n').encode()+b'\x1a'
        prog=2+sum(3+len(line.split(' ',1)[1]) for line in lines)
        assert prog+len(data)<=0x6000<prog+((len(data)+255)//256)*256
        path,text=self.run('capture-edge',[('LOAD "1:seed"',80000),('SAVE "1:edge",A',50000),
                           ('NEW',200),('LOAD "1:edge"',80000),('CLS:RUN',2000)],disk_with_program(lines))
        assert 'edgeok' in text and 'error' not in text,text
        image=(path/'disk.d88').read_bytes()
        assert file_data(image,'edge')==data, '境界直前のSAVE本文'
        assert file_data(image,'edge',padding=True)[len(data):]==bytes((-len(data))%256), '末尾ゼロ詰め'
        self.ok('空き17BのSAVE→LOAD、末尾セクタの境界保護')

    def symbols(self):
        body=[]
        for i in range(60):
            body.append(f'V{i}={i+100}')
            if i<8:body.extend([f'DIM A{i}(2)',f'A{i}(1)={i+200}'])
        body.extend(['A0(1)=V59+A7(1)+W','B=0'])
        body += [f'IF V{i}<>{i+100} THEN B=B+1' for i in range(60)]
        body += [f'IF A{i}(1)<>{(366 if i==0 else i+200)} THEN B=B+1' for i in range(8)]
        body += ['CLS:PRINT "SYMOK";B;A0(1);V0;V59;A7(1)','END']
        lines=[f'{(i+1)*10} {line}' for i,line in enumerate(body)]
        _,text=self.run('symbols',[('LOAD "1:seed"',50000),('RUN',20000)],disk_with_program(lines))
        assert re.search(r'symok\s*0\s+366\s+100\s+159\s+207',text) and 'error' not in text,text
        self.ok('単純変数60個＋配列8個の混在・全値読み戻し・評価中の追記')

    def strings(self):
        commands=[(f'S{i}$="'+chr(65+i%26)*40+'"',200) for i in range(24)]
        commands+=[('B=0',160)]
        for i in range(24):
            commands += [(f'IF S{i}$<>"'+chr(65+i%26)*40+'" THEN B=B+1',250)]
        # 短値でページを解放し、その穴へ再割当て。既存長値は同じページを再利用する。
        commands += [('S3$="x"',200),('S24$="'+('Z'*40)+'"',200),('S4$="'+('Y'*41)+'"',200),
                     ('CLS:PRINT "STROK";B;LEN(S3$);LEN(S24$);LEN(S4$)',200)]
        lines=[f'{(i+1)*10} {line}' for i,(line,_) in enumerate(commands)]
        _,text=self.run('strings',[('LOAD "1:seed"',50000),('RUN',20000)],disk_with_program(lines))
        assert re.search(r'strok\s*0\s+1\s+40\s+41',text) and 'error' not in text.lower(),text
        self.ok('40文字の文字列24個・全値読み戻し・解放/穴の再利用/長値再代入')

    def edits(self):
        commands=[('10 V=123:DIM A(2):A(1)=456:S$="'+('X'*40)+'"',200),
                  ('20 STOP',200),('30 END',200),('RUN',400),('15 REM EDIT',200),
                  ('CLS:PRINT "EDITOK";V;A(1);LEN(S$)',200),('CONT',300)]
        _,text=self.run('edit',commands)
        assert re.search(r'editok\s*0\s+0\s+0',text) and "can't continue" in text,text
        self.ok('編集で変数/配列/文字列消去、CONT ERR17')

    def limits(self):
        _,text=self.run('limit-slope',[
            ('CLEAR ,49152:PRINT "FREEA";FRE(0)',160),
            ('CLEAR ,50176:PRINT "FREEB";FRE(0)',160),
            ('PRINT "FREESTR";FRE("")',160)])
        values=[int(re.search(label+r"\s*(\d+)",text)[1])
                for label in ('freea','freeb','freestr')]
        assert values[1]-values[0]==1024 and values[2]==values[1],text
        self.ok('CLEAR ,aの差1024とFREの差一致、文字列引数も同値')
        for n in (99,128,256,512,1024,2048):
            commands=[('10 CLEAR ,49152',160),('20 CLEAR ,,'+str(n),160),
                      ('30 D=0:GOSUB 100',160),('40 END',160),
                      ('100 D=D+1:GOSUB 100',160),('RUN',1500),
                      ('CLS:PRINT "DEPTH";D',160)]
            path,text=self.run('depth-'+str(n),commands,trace_at=300,
                               trace_range='BF00-C000')
            assert re.search(r'depth\s*'+str((n-92)//7)+r'\b',text),text
            assert 'error' not in text,text
        self.ok('CLEAR ,,nのGOSUB深さfloor((n-92)/7)、99/128/256/512/1024/2048（279段）')
        commands=[('10 PRINT "KEPT";PEEK(49152):END',160),
                  ('CLEAR ,49151',160),('POKE 49152,73',160),('RUN',500),('RUN',500)]
        path,text=self.run('above-limit',commands,trace_at=300,trace_range='C000-C000')
        assert len(re.findall(r'kept\s*73\b',text))==2,text
        writes=[line.split() for line in (path/'writes.tsv').read_text().splitlines()
                if len(line.split())==5 and line.split()[3]=='C000']
        assert [row[4] for row in writes]==['49'],writes
        self.ok('上限49151より上のPOKE値73をRUN二回が保持、追加書込みなし')
        # 対応するNEXTをすべて後置し、溢れる前に完了したFOR本体の段数を読む。
        for n in (128,256,512,1024,2048):
            depth=(n-80)//19
            count=depth+1
            names=[f'F{i}' for i in range(count)]
            lines=[f'10 CLEAR ,49152,{n}','20 D=0']
            lines += [f'{100+i*10} FOR {name}=0 TO 0:D={i+1}'
                      for i,name in enumerate(names)]
            lines += [f'{100+count*10+i*10} NEXT {name}'
                      for i,name in enumerate(reversed(names))]
            _,text=self.run('for-depth-'+str(n),[('LOAD "1:seed"',50000),
                           ('RUN',1500),('PRINT "FORDEPTH";D',160)],disk_with_program(lines))
            assert 'out of memory' in text and re.search(r'fordepth\s*'+str(depth)+r'\b',text),text
        self.ok('CLEAR ,,nのFOR深さfloor((n-80)/19)、128/256/512/1024/2048、溢れERR7')
        # NEXTの字面が文字列/REM/DATA/識別子の中だけなら、FOR本体の前にERR26。
        for tag,tail in [('string','PRINT "NEXT"'),('rem','REM NEXT'),
                         ('data','DATA "x:NEXT",NEXT'),('identifier','NEXT1=0'),
                         ('suffix','NEXT$="x"')]:
            lines=['10 FOR I=1 TO 1:D=73','20 '+tail]
            _,text=self.run('for-no-next-'+tag,[(line,160) for line in lines]+[
                           ('RUN',500),('PRINT "SCANVALUE";D',160)])
            assert 'for without next' in text and re.search(r'scanvalue\s*0\b',text),text
        _,text=self.run('for-direct-no-next',[
            ('FOR I=1 TO 1:PRINT "NEXT"',500)])
        assert 'for without next' in text,text
        _,text=self.run('for-data-next',[(line,160) for line in [
            '10 FOR I=1 TO 1:D=73:END','20 DATA "x:NEXT",NEXT:NEXT I']]+[
            ('RUN',500),('PRINT "SCANDONE";D',160)])
        assert re.search(r'scandone\s*73\b',text) and 'error' not in text,text
        self.ok('FORの事前NEXT検査、文字列/REM/DATA/識別子/接尾辞除外・直接行末・DATA後のNEXT')
        # FOR 19Bを使ったまま再帰するとGOSUBに使える共用域が減る。
        lines=['10 CLEAR ,49152,121','20 FOR I=0 TO 0:D=0:GOSUB 100',
               '30 NEXT:END','100 D=D+1:GOSUB 100']
        _,text=self.run('shared-stack',[(line,160) for line in lines]+[
                       ('RUN',500),('PRINT "SHARED";D',160)])
        assert 'out of memory' in text and re.search(r'shared\s*1\b',text),text
        self.ok('FOR/GOSUB共用域の衝突でERR7（n=121、19B＋7B×1、GOSUB余白92B）')

    def exhaustion(self):
        # ページ不足とヒープ不足を各々起こし、既存値とBASIC復帰を確認。
        lines=[f'{(i+1)*10} S{i}$="'+('X'*40)+'"' for i in range(90)]
        commands=[('LOAD "1:seed"',50000),('RUN',20000)]
        commands += [('CLS:PRINT "PAGEOOM";LEN(S0$)',200),('S89$="'+('X'*40)+'"',200),
                     ('CLEAR',200),('PRINT "RECOVER";2+3',200)]
        _,text=self.run('page-oom',commands,disk_with_program(lines))
        assert 'out of memory' in text and re.search(r'pageoom\s*40',text) and re.search(r'recover\s*5',text),text
        # 型別配列では単精度32要素の論理消費は137B。旧84個では不足しない。
        # 256個なら論理消費だけで35072Bとなり、既定CLEARの空き容量を超える。
        array_count=256
        lines=[f'{(i+1)*10} DIM A{i}(31)' for i in range(array_count)]
        commands=[('LOAD "1:seed"',50000),('RUN',20000)]
        commands += [('CLS:PRINT "HEAPOOM";A0(0)',200),(f'DIM A{array_count}(31)',200),('CLEAR',200),('PRINT "RECOVER";7',200)]
        _,text=self.run('heap-oom',commands,disk_with_program(lines))
        assert 'out of memory' in text and re.search(r'heapoom\s*0',text) and re.search(r'recover\s*7',text),text
        # 本文不足時の置換は旧本文を失わない。
        lines=[f'{i*10} REM '+('X'*64) for i in range(1,360)]
        _,text=self.run('program-oom',[('LOAD "1:seed"',120000),('PRINT "LIVE";9',200)],disk_with_program(lines))
        assert 'out of memory' in text and re.search(r'live\s*9',text),text
        # SAVE捕捉不足。本文が収まっても展開文字列を置けなければERR7。
        lines=[f'{i*10} REM '+('X'*24) for i in range(1,451)]
        _,text=self.run('capture-oom',[('LOAD "1:seed"',120000),('CLS:SAVE "1:full",A',4000),
                                     ('PRINT "LIVE";11',200)],disk_with_program(lines))
        assert 'out of memory' in text and re.search(r'live\s*11',text),text
        self.ok('ページ/ヒープ/本文/SAVE捕捉の不足でERR7、既存値保持とBASIC復帰')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work-dir',type=Path)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='pc88-memdyn-') as temp:
        work=args.work_dir or Path(temp)
        work.mkdir(parents=True,exist_ok=True)
        suite=Suite(work)
        suite.large();suite.wide_capture();suite.capture_edge();suite.symbols();suite.strings();suite.edits();suite.limits();suite.exhaustion()
        print('l4_memdyn_selftest: OK（全13群、自作ROM/自作媒体のみ）')

if __name__=='__main__':
    main()
