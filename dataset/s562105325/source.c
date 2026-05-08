#include<stdio.h>
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
	int A, B, K, i;
	scanf("%d %d %d", &A, &B, &K);
	if (A + (K - 1) >= B - (K - 1)){
		for (i = A; i <= B; i++) {
			printf("%d\n", i);
		}
	}
	else {
		for (i = A; i <= A + (K - 1); i++) {
			printf("%d\n", i);
		}
		for (i = B - (K - 1); i <= B; i++) {
			printf("%d\n", i);
		}
	}
	return 0;
}
