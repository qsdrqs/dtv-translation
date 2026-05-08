// AOJ 0581: Gifts
// 2018.1.3 bal4u@uu

#include <stdio.h>
#include <ctype.h>
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

int H, W, K;
char map[52][52];
int memo[1<<12][4][50][50];
int mask;
int mv[4][2] = {{0,1},{1,0},{0,-1},{-1,0}};

int calc(int b, int lu, int r, int c)
{
	int i, k, pr, pc, nr, nc, f, ans;
	
	if (memo[b][lu][r][c] != -1) return memo[b][lu][r][c];
	if (lu == 0 && r == H-1 && c == W-1) return 0;

	k = K<<1, pr = r, pc = c, f = 0;
	for (i = 0; i < k; i++) {
		pr += -mv[(b>>(i<<1)) & 3][0];
		pc += -mv[(b>>(i<<1)) & 3][1];
		if (pr == r && pc == c) { f = 1; break; }
	}
	if (!f && isdigit(map[r][c])) k = map[r][c] & 0xf; else k = 0;

	ans = -1000;
	for (i = 0; i < 4; i++) {
		if (lu == 0 && i >= 2) break;
		nr = r + mv[i][0], nc = c + mv[i][1];
		if (nr >= 0 && nr < H && nc >= 0 && nc < W && map[nr][nc] != '#') {
			int x = calc(((b << 2) | i) & mask, lu - (i >= 2), nr, nc) + k;
			if (ans < x) ans = x;
		}
	}
	return memo[b][lu][r][c] = ans;
}

int main()
{
	int r, ans;
	
	scanf("%d%d%d", &H, &W, &K);
	mask = (1<<(K<<2)) - 1;
	memset(memo, -1, sizeof(memo));
	for (r = 0; r < H; r++) scanf("%s", map[r]);
	ans = calc(0, K, 0, 0);	if (ans < 0) ans = 0;
	printf("%d\n", ans);
	return 0;
}
