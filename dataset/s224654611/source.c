#include<stdio.h>
#include<stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main() {
	int N;
	int *A;
	int loop;
	unsigned long long int sum = 0;

	scanf("%d", &N);
	A = malloc(sizeof(int)*N);
	for (loop = 0; loop < N; loop++)
		scanf("%d", &A[loop]);

	for (loop = 0; loop < N - 1; loop++) {
		sum += A[loop] / 2;
		if (A[loop] % 2 != 0 && A[loop + 1] != 0) {
			sum++;
			A[loop + 1]--;
		}
	}
	sum += A[N - 1] / 2;

	printf("%ld\n", sum);
	return 0;
}
