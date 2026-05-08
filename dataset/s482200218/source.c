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

int main(){
	int n,h,m;
	char a[10];
	double h2,m2,ggg;
	scanf("%d",&n);
	while(n-->0){
		scanf("%s",a);
		h=(a[0]-'0')*10+a[1]-'0';
		m=(a[3]-'0')*10+a[4]-'0';
		h2=(double)360*(h*60+m)/(60*12);
		m2=(double)360*m/60;

		if(h2<m2)
			ggg=m2-h2;
		else
			ggg=h2-m2;
		
		
		if(ggg>=0&&ggg<30)
			printf("alert\n");
		else if(ggg>=90&&ggg<=270)
			printf("safe\n");
		else if(ggg<360&&330<ggg)
			printf("alert\n");
		else printf("warning\n");
		
		
		
	}
	return 0;
}