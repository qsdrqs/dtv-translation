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

int d[5001];

int main()
{
	int n;
	int i,j;
	int max;
	int sum;
	for(i=0;i<5001;i++){
		d[i]=0;
	}
	while(1){
		scanf("%d",&n);
		if(n==0)break;
		for(i=0;i<n;i++){
			scanf("%d",&d[i]);
			if(i!=0) d[i]+=d[i-1];
		}
		sum=d[0];
		for(i=0;i<n;i++){
			if(d[i]>sum) sum=d[i];
			for(j=0;j<i;j++){
				if((d[i]-d[j])>sum) sum=d[i]-d[j];
			}
		}
		printf("%d\n",sum);
	}
	return 0;
}