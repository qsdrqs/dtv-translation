#include <stdio.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main(void) {
	int N;
	int A[128];
	int sum[128];
	int i;
	int ok, ng;
	if (scanf("%d", &N) != 1) return 1;
	sum[0] = 0;
	for (i = 1; i <= N; i++) {
		if (scanf("%d", &A[i]) != 1) return 1;
		sum[i] = sum[i - 1] + A[i];
	}
	ok = 0;
	ng = sum[N] + 1;
	while (ok + 1 < ng) {
		int mid = ok + (ng - ok) / 2;
		int dekiru = 1;
		for (i = 1; i <= N; i++) {
			if (sum[i] < mid * i) dekiru = 0;
		}
		if (dekiru) ok = mid; else ng = mid;
	}
	printf("%d\n", ok);
	return 0;
}

