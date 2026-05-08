#include <stdio.h>

#define INF 999999999

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int H, W;
int a[64][64];
int b[64][64];

int h, w;
int c[64][64];

int main(void) {
	int i, j;
	int answer = -INF;
	if (scanf("%d%d", &H, &W) != 2) return 1;
	for (i = 0; i < H; i++) {
		for (j = 0; j < W; j++) {
			if (scanf("%d", &a[i][j]) != 1) return 1;
		}
	}
	for (i = 0; i < H; i++) {
		for (j = 0; j < W; j++) {
			if (scanf("%d", &b[i][j]) != 1) return 1;
		}
	}
	if (scanf("%d%d", &h, &w) != 2) return 1;
	for (i = 0; i < h; i++) {
		for (j = 0; j < w; j++) {
			if (scanf("%d", &c[i][j]) != 1) return 1;
		}
	}
	for (i = 0; i <= H - h; i++) {
		for (j = 0; j <= W - w; j++) {
			int ok = 1;
			int k, l;
			int score = 0;
			for (k = 0; k < h; k++) {
				for (l = 0; l < w; l++) {
					score += a[i + k][j + l];
					if (b[i + k][j + l] != c[k][l]) ok = 0;
				}
			}
			if (ok && score > answer) answer = score;
		}
	}
	if (answer == -INF) puts("NA"); else printf("%d\n", answer);
	return 0;
}

