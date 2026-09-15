10 dim a(6)
20 a(1)=5
30 a(2)=3
40 a(3)=8
50 a(4)=1
60 a(5)=9
70 a(6)=2
80 for i=1 to 5
90 for j=1 to 5
100 if a(j)>a(j+1) then 130
110 goto 160
130 t=a(j)
140 a(j)=a(j+1)
150 a(j+1)=t
160 next j
170 next i
180 for k=1 to 6
190 print a(k);
200 next k
