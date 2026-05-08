/*
  Aizu Vol-0 0098: Maximum Sum Sequence II 
  2017.8.15 bal4u@uu
  ????????????????????§???
*/

#include <stdio.h>

#define MAX 100

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int a[MAX + 5][MAX + 5], N;
int s[MAX + 5][MAX + 5];

int main()
{
	int r, c, r2, c2, k, max;

	scanf("%d", &N);
	for (r = 1; r <= N; r++) for (c = 1; c <= N; c++) scanf("%d", a[r] + c);
	for (r = 1; r <= N; r++)
		for (s[r][1] = a[r][1], c = 2; c <= N; c++) s[r][c] += s[r][c-1] + a[r][c];
	max = a[1][1];
	for (r = 1; r <= N; r++) for (c = 1; c <= N; c++) {
		for (c2 = c; c2 <= N; c2++) {
			k = s[r][c2] - s[r][c - 1];	if (k > max) max = k;
			for (r2 = r + 1; r2 <= N; r2++) { k += s[r2][c2] - s[r2][c - 1]; if (k > max) max = k; }
		}
	}
	printf("%d\n", max);
	return 0;
}