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

typedef struct {
	int key, id;
} data;

void merge_sort(data x[], int n)
{
	static data y[200001] = {};
	if (n <= 1) return;
	merge_sort(&(x[0]), n/2);
	merge_sort(&(x[n/2]), (n+1)/2);
	
	int i, p, q;
	for (i = 0, p = 0, q = n/2; i < n; i++) {
		if (p >= n/2) y[i] = x[q++];
		else if (q >= n) y[i] = x[p++];
		else y[i] = (x[p].key < x[q].key)? x[p++]: x[q++];
	}
	for (i = 0; i < n; i++) x[i] = y[i];
}

int main()
{
	int i, N, A[200001], B[200001];
	scanf("%d", &N);
	for (i = 0; i < N; i++) scanf("%d %d", &(A[i]), &(B[i]));
	
	int min, max;
	data d[200001];
	for (i = 0; i < N; i++) {
		d[i].key = A[i];
		d[i].id = i;
	}
	merge_sort(d, N);
	min = (N % 2 == 1)? d[N/2].key: d[N/2-1].key + d[N/2].key;
	for (i = 0; i < N; i++) {
		d[i].key = B[i];
		d[i].id = i;
	}
	merge_sort(d, N);
	max = (N % 2 == 1)? d[N/2].key: d[N/2-1].key + d[N/2].key;

	printf("%d\n", max - min + 1);
	fflush(stdout);
	return 0;
}