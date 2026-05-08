#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
	char name[24];
	int zikan;
	int syunyu;
} sakumotu_t;

int qsort_comp(const void* x,const void* y) {
	const sakumotu_t* a=(const sakumotu_t*)x;
	const sakumotu_t* b=(const sakumotu_t*)y;
	long long a_koritu=(long long)(a->syunyu)*(b->zikan);
	long long b_koritu=(long long)(b->syunyu)*(a->zikan);
	if(a_koritu<b_koritu)return 1;
	if(a_koritu>b_koritu)return -1;
	return strcmp(a->name,b->name);
}

int main(void) {
	int N;
	sakumotu_t sakumotu[50];
	int P,A,B,C,D,E,F,S,M;
	int i;
	while(1) {
		scanf("%d",&N);
		if(N==0)break;
		for(i=0;i<N;i++) {
			scanf("%s",sakumotu[i].name);
			scanf("%d%d%d%d%d%d%d%d%d",&P,&A,&B,&C,&D,&E,&F,&S,&M);
			sakumotu[i].zikan=A+B+C+D+E+(D+E)*(M-1);
			sakumotu[i].syunyu=F*S*M-P;
		}
		qsort(sakumotu,N,sizeof(sakumotu_t),qsort_comp);
		for(i=0;i<N;i++)puts(sakumotu[i].name);
		puts("#");
	}
	return 0;
}