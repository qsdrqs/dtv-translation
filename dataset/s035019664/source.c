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
	int i,j;
	int ans;
	int n,a,b,c,x;
	int y[100];
 
	while(scanf("%d%d%d%d%d",&n,&a,&b,&c,&x),n){
		for(i = 0;i < n;i++){
			scanf("%d",&y[i]);
		}
if(n==1&&x==y[0]){printf("0\n");continue;}
		j = 0;
		
		if(y[j] == x)j++;

		for(i = 0;i < 10000;i++){
			x = (a * x + b) % c;
			if(x == y[j]){
				j++;
			}
			if(n == j)break;
		}
		if(i == 10000)i = -2;
		i++;
		printf("%d\n",i);
	}
	return 0;
}