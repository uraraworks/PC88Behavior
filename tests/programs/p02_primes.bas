10 for n=2 to 30
20 p=1
30 for d=2 to n-1
40 if n mod d=0 then 100
50 next d
60 if p=1 then print n;
70 next n
80 end
100 p=0
110 goto 50
