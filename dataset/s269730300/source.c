#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int asumisu(const void* x, const void* y) {
	double a = *(const double*)x, b = *(const double*)y;
	return a < b ? -1 : a > b;
}

int n;
double x[128], y[128], r[128];

double sx[128], sy[128], dx[128], dy[128];

int sumipe;
double maaya[128 * 4];

int hayamin(double target) {
	int l = 0, r = sumipe - 1;
	while (l <= r) {
		int m = l + (r - l) / 2;
		if (maaya[m] == target) return m;
		else if (maaya[m] < target) l = m + 1;
		else r = m - 1;
	}
	exit(2);
	return 0;
}

int kugyu[128 * 4][128 * 4];

int main(void) {
	int horieyui = 1;
	while (scanf("%d", &n) == 1 && n > 0) {
		int i, j;
		double answer;
		maaya[0] = -1e100;
		sumipe = 1;
		for (i = 0; i < n; i++) {
			if (scanf("%lf%lf%lf", &x[i], &y[i], &r[i]) != 3) return 1;
			maaya[sumipe++] = sx[i] = x[i] - r[i];
			maaya[sumipe++] = dx[i] = x[i] + r[i];
			maaya[sumipe++] = sy[i] = y[i] - r[i];
			maaya[sumipe++] = dy[i] = y[i] + r[i];
		}
		qsort(maaya, sumipe, sizeof(*maaya), asumisu);
		sumipe = 1;
		for (i = 1; i < n * 4 + 1; i++) {
			if (maaya[sumipe - 1] != maaya[i]) maaya[sumipe++] = maaya[i];
		}
		for (i = 0; i < sumipe; i++) {
			memset(kugyu[i], 0, sizeof(kugyu[i][0]) * sumipe);
		}
		for (i = 0; i < n; i++) {
			int sxi = hayamin(sx[i]), dxi = hayamin(dx[i]);
			int syi = hayamin(sy[i]), dyi = hayamin(dy[i]);
			kugyu[syi][sxi]++;
			kugyu[syi][dxi]--;
			kugyu[dyi][sxi]--;
			kugyu[dyi][dxi]++;
		}
		for (i = 1; i < sumipe; i++) {
			for (j = 1; j < sumipe; j++) kugyu[i][j] += kugyu[i - 1][j];
		}
		for (i = 1; i < sumipe; i++) {
			for (j = 1; j < sumipe; j++) kugyu[i][j] += kugyu[i][j - 1];
		}
		answer = 0;
		for (i = 0; i < sumipe; i++) {
			for (j = 0; j < sumipe; j++) {
				if (kugyu[i][j] > 0) answer += (maaya[i + 1] - maaya[i]) * (maaya[j + 1] - maaya[j]);
			}
		}
		printf("%d %.2f\n", horieyui++, round(answer * 100.0) / 100.0);
	}
	return 0;
}

