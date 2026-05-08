#include<stdio.h>
#include<string.h>
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
	long long int  n, a, b, memo;
	char s[105][105];
	scanf("%lld%lld",&a,&b);
	printf("100 100\n");
	for (int i = 1; i <= 50; i++) {
		for (int j = 1; j <= 100; j++) {
			s[i][j] = '.';
		}
	}
	for (int i = 51; i <= 100; i++) {
		for (int j = 1; j <= 100; j++) {
			s[i][j] = '#';
		}
	}

	for (int i = 1; i <= 50; i++) {
		for (int j = 1; j <= 100; j++) {
			if (j % 2 == 0 && i % 2 == 1 && b != 1) { s[i][j] = '#'; b--; }
		}
	}
	for (int i = 51; i <= 100; i++) {
		for (int j = 1; j <= 100; j++) {
			if (j % 2 == 0 && i % 2 == 0 && a != 1) { s[i][j] = '.'; a--; }
		}
	}
	for (int i = 1; i <= 100; i++) {
		for (int j = 1; j <= 100; j++) {
			printf("%c", s[i][j]);
		}
		printf("\n");
	}
}
