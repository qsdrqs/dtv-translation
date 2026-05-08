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

int memo[32][32];
int map[32][32];
int w, h;

int dfs(int x, int y, int px){
	int ny = y + 1;

	if (x < 0 || x >= w) return (0);
	if (y >= h) return (1);
	if (memo[y][x] != -1) return (memo[y][x]);

	if (y == h - 1 && map[y][x] == 0) return (memo[y][x] = 1);

	switch (map[y][x]){
	  case 0: return (memo[y][x] = dfs(x, ny, x) + dfs(x + 1, ny, x) + dfs(x - 1, ny, x));
	  case 1: return (memo[y][x] = 0);
	  case 2: return (x == px ? dfs(x, ny + 1, x) : 0);
	  default:fprintf(stderr, "%d is invalid value\n", map[y][x]);
	}
}

int main(void)
{
	while (scanf("%d %d", &w, &h), w){
		int ans = 0;
		int i, j;

		for (i = 0; i < h; i++){
			for (j = 0; j < w; j++){
				scanf("%d", map[i] + j);
			}
		}

		memset(memo, -1, sizeof(memo));
		for (i = 0; i < w; i++){
			ans += dfs(i, 0, i);
		}

		printf("%d\n", ans);
	}

	return (0);
}