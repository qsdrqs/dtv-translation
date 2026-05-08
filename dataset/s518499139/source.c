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

int main(void) {
	int n;
	int nn;
	int a,b,cd;
	long long count;
	while(scanf("%d",&n)==1) {
		nn=(n<=1000?n:1000);
		count=0;
		for(a=0;a<=nn;a++) {
			for(b=0;b<=nn;b++) {
				cd=n-a-b;
				if(cd<0)break;
				else if(cd>2000)continue;
				if(cd<=1000)count+=cd+1;
				else {
					int over=cd-1000;
					count+=1000-over+1;
				}
			}
		}
		printf("%lld\n",count);
	}
	return 0;
}