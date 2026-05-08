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

int min(int a, int b, int c, int d)
{
	int r;
	
	if (a < b){
		r = a;
	}
	else {
		r = b;
	}
	if (c < r){
		r = c;
	}
	if (d < r){
		r = d;
	}
	
	return (r);
}

int main(void)
{
	int N;
	int i, K;
	int x, y;
	
	scanf("%d %d", &N, &K);
	
	for (i = 0; i < K; i++){
		scanf("%d %d", &x, &y);
		
		printf("%d\n", min(x - 1, y - 1, N - x, N - y) % 3 + 1);
	}
	
	return (0);
}