// AOJ 2153: Mirror Cave
// 2017.11.11 bal4u@uu

#include <stdio.h>
#include <string.h>
#define TM 0
#if TM
#include <time.h>
#endif

#define QMAX 150000
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct { char lr, lc, rr, rc; } Q;
Q q[QMAX+2]; int top, end;

char ml[52][52], mr[52][52];
char mk[52][52][52][52];
int mvl[4][2] = {{-1,0},{0,1},{1,0},{0,-1}};
int mvr[4][2] = {{-1,0},{0,-1},{1,0},{0,1}};

int main()
{
	int w, h, r, c, lr, lc, rr, rc, lr2, lc2, rr2, rc2, i, f;
	int slr, slc, srr, src, ans;
#if TM
	clock_t start, end;
	start = clock();
#endif
	for (r = 0; r <= 51; r++) ml[r][0] = mr[r][0] = '#';
	for (c = 0; c <= 51; c++) ml[0][c] = mr[0][c] = '#';

	while (scanf("%d%d", &w, &h) && w > 0) {
		for (f = 0, r = 1; r <= h; r++) {
			scanf("%s%s", ml[r]+1, mr[r]+1);
			if (f < 3) for (c = 1; c <= w; c++) {
				if (ml[r][c] == 'L') slr = r, slc = c, f |= 1;
				if (mr[r][c] == 'R') srr = r, src = c, f |= 2;
			}
		}
		for (r = 1; r <= h; r++) ml[r][w+1] = mr[r][w+1] = '#';
		for (c = 1; c <= w; c++) ml[h+1][c] = mr[h+1][c] = '#';

		memset(mk, 0, sizeof(mk));
		q[0].lr = slr, q[0].lc = slc, q[0].rr = srr, q[0].rc = src, top = 0, end = 1;
		mk[slr][slc][srr][src] = 1;
		ans = 0;
		while (top != end) {
			lr = q[top].lr, lc = q[top].lc, rr = q[top].rr, rc = q[top].rc;
			if (++top == QMAX) top = 0;
			if (ml[lr][lc] == '%' && mr[rr][rc] == '%') { ans = 1; break; }
			if (ml[lr][lc] == '%' || mr[rr][rc] == '%') continue;

			for (i = 0; i < 4; i++) {
				lr2 = lr + mvl[i][0], lc2 = lc + mvl[i][1];
				rr2 = rr + mvr[i][0], rc2 = rc + mvr[i][1];
				if (ml[lr2][lc2] == '#') lr2 = lr, lc2 = lc;
				if (mr[rr2][rc2] == '#') rr2 = rr, rc2 = rc;
				if (mk[lr2][lc2][rr2][rc2]) continue;
				mk[lr2][lc2][rr2][rc2] = 1;
				q[end].lr = lr2, q[end].lc = lc2, q[end].rr = rr2, q[end].rc = rc2;
				if (++end == QMAX) end = 0;
			}
		}
		puts(ans ? "Yes" : "No");
	}
#if TM
	end = clock();
	printf("time %lf\n", (double)(end-start)/CLOCKS_PER_SEC);
#endif
	return 0;
}