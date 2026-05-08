#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>

#define P 1000000007

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int comp(const void *a, const void *b){return *(int*)a-*(int*)b;}
int compw(const void *a, const void *b){return (*(int*)a>*(int*)b)-(*(int*)a<*(int*)b);}
int compr(const void *a, const void *b){return *(int*)b-*(int*)a;}

uint32_t nextpint(void){
	uint_fast32_t x=0;
	while(1){
		uint_fast8_t c=getchar();
		if('0'<=c && c<='9'){
			x=x*10+c-'0';
		}else{
			break;
		}
	}
	return x;
}

int b[100000];
int main(void){
	int n, h, i;
	n=nextpint();
	h=nextpint();
	int a=0;
	for(i=0; i<n; i++){
		int A=nextpint();
		if(A>a) a=A;
		b[i]=nextpint();
	}
	qsort(b, n, sizeof(int), compr);
	for(i=0; i<n; i++){
		if(h<=0 || b[i]<=a) break;
		h-=b[i];
	}
	printf("%d\n", h>0?i+(h+a-1)/a:i);
}
