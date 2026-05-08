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

int main()
{
	int i,N,c[1000],a[1000],n[1000],s[100]={0};
	scanf("%d",&N);
	for(i=0;i<	N;i++){
		scanf("%d %d %d",&c[i],&a[i],&n[i]);
		while(1){
			if(c[i]>0&&a[i]>0&&n[i]>0){
				s[i]++;
				c[i]--;
				a[i]--;
				n[i]--;
			}
			 else if(c[i]>1&&a[i]>0){
				 s[i]++;
				 c[i]-=2;
				 a[i]--;
			 }
			 else if(c[i]>2){
				 s[i]++;
				 c[i]-=3;
			 }
			 else break;
		}
	}
	for(i=0;i<N;i++){
	printf("%d\n",s[i]);
	}
	return 0;
}