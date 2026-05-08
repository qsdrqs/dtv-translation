#include <stdio.h>
#include <stdlib.h>

#define N_MAX 65000

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int qsc_uint(const void* x,const void* y) {
	unsigned int a=*((const unsigned int*)x);
	unsigned int b=*((const unsigned int*)y);
	if(a>b)return 1;
	if(a<b)return -1;
	return 0;
}

int main(void) {
	unsigned int n;
	while(scanf("%u",&n)==1 && n>0) {
		unsigned int plen_sum=0;
		static unsigned int jlen[N_MAX];
		unsigned int max=0;
		unsigned int i;
		for(i=0;i<n;i++) {
			unsigned int plen;
			scanf("%u",&plen);
			plen_sum+=plen;
		}
		for(i=0;i<n-1;i++) {
			scanf("%u",&jlen[i]);
			plen_sum+=jlen[i];
		}
		qsort(jlen,n-1,sizeof(jlen[0]),qsc_uint);
		for(i=1;i<=n;i++) {
			if(i*plen_sum>max)max=i*plen_sum;
			if(i<n)plen_sum-=jlen[i-1];
		}
		printf("%u\n",max);
	}
	return 0;
}