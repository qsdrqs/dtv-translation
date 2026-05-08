#include<stdio.h>
#include<stdlib.h>
#include<string.h>
#include<math.h>
 
#define INF 1000000000
 
#define min(a,b) (((a)<(b))?(a):(b))
#define max(a,b) (((a)>(b))?(a):(b))

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
	long N, K;
	long ans = 0;
	char D[11][4];
	long i, j;
	char buf[100];
	
	scanf("%ld %ld", &N, &K);
	for(i=1;i<=K;i++) {
		scanf("%s", D[i]);
	}
	
	ans = N;
	while(1) {
		sprintf(buf, "%ld", ans);
		for(i=1;i<=K;i++) {
			if(strstr(buf, D[i]) != NULL) break;
		}
		if(i > K) break;
		ans++;
	}
	
	printf("%ld\n", ans);
	
	return 0;
}