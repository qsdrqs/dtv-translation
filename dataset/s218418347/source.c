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

int n,m,i,j,k,t[16],c[16],p,d;
int main(void){
	for(*t=n=1;++i<16;)t[i]=n*=3;
	for(;scanf("%d%d",&n,&m),n;){
		for(k=3;k--;)
			for(scanf("%d",&i);i--;c[j]=k)scanf("%d",&j);
		for(p=j=k=0;k++<n;)
				j+=t[n-k]*abs(i=p-c[k]),p=i%2*2+p&3;
		j=fmin(j,t[n]+~j);
		printf("%d\n",j>m?-1:j);
	}
	return 0;
}