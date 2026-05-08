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
	int m, f, b;
	scanf("%d%d%d", &m, &f, &b);
	if (m + f >= b) {
		if (m >= b) {
			printf("0\n");
		}
		else {
			printf("%d\n",b-m);
		}
	}
	else {
		printf("NA\n");
	}
	return 0;
}
