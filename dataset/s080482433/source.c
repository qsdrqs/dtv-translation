// AOJ 	2302: On or Off
// 2018.1.31 bal4u

#include <stdio.h>
#include <string.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct { int r, c, t; } Q;
Q q[2600]; int top, end;

char map[53][53];
char pr[53][53], prev[53][53][2];		// prev (r,c)
int keep[53][53], onoff[53][53];
int cost[53][53];
int visited[53][53];
char mk[53][53];
int mv[4][2] = {{-1,0},{0,1},{1,0},{0,-1}};

#define getchar_unlocked()  getchar()
int in()
{
	int n = 0;
	int c = getchar_unlocked();
	do n = (n<<3)+(n<<1) + (c & 0xf), c = getchar_unlocked();
	while (c >= '0');
	return n;
}

int main()
{
	int R, C, M, i, k, r, c, t, nr, nc, sr, sc, gr, gc, tm, ans;
	
	R = in(), C = in(), M = in();
	memset(map, 1, sizeof(map));
	for (r = 1; r <= R; r++) {
		fgets(map[r]+1, 53, stdin);
		for (c = 1; c <= C; c++) map[r][c] &= 1;
		map[r][C+1] = 1;
	}
	for (r = 1; r <= R; r++) for (c = 1; c <= C; c++) keep [r][c] = in();
	for (r = 1; r <= R; r++) for (c = 1; c <= C; c++) onoff[r][c] = in();
	for (r = 1; r <= R; r++) for (c = 1; c <= C; c++) onoff[r][c]+= in();

	tm = 1;
	sr = in()+1, sc = in()+1;
	visited[sr][sc] = tm;
	while (--M) {
		gr = in()+1, gc = in()+1;
		memset(mk, 0, sizeof(mk));
		q[0].r = sr, q[0].c = sc, q[0].t = tm, top = 0, end = 1;
		while (top != end) {
			r = q[top].r, c = q[top].c, t = q[top++].t;
			if (r == gr && c == gc) break;
			if (mk[r][c]) continue;
			mk[r][c] = 1;
			for (i = 0; i < 4; i++) {
				nr = r+mv[i][0], nc = c+mv[i][1];
				if (map[nr][nc] || mk[nr][nc]) continue;
				prev[nr][nc][0] = r, prev[nr][nc][1] = c;
				q[end].r = nr, q[end].c = nc, q[end++].t = t+1;
			}
		}
		nr = gr, nc = gc, tm = t;
		while (nr != sr || nc != sc) {
			if (visited[nr][nc]) {
				k = (t - visited[nr][nc])*keep[nr][nc];
				if (k > onoff[nr][nc]) k = onoff[nr][nc];
				cost[nr][nc] += k;
			}
			visited[nr][nc] = t;
			r = prev[nr][nc][0], c = prev[nr][nc][1], t--;
			nr = r, nc = c;
		}
		sr = gr, sc = gc;
	}

	ans = 0;
	for (r = 1; r <= R; r++) for (c = 1; c <= C; c++) {
		if (visited[r][c]) ans += cost[r][c] + onoff[r][c];
	}
	printf("%d\n", ans);
	return 0;
}
