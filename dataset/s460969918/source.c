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

int main(void){
	int t, n, s, f;
	
	while(1){
	int total = 0;
	scanf("%d", &t);
	if(t == 0) return 0;
	scanf("%d", &n);
	
	while(n > 0){
		scanf("%d %d", &s, &f);
		total = total + (f - s);
		n--;
	}
	
	if(total >= t){
		printf("OK\n");
	}
	
	if(total <t){
		printf("%d\n",t - total);
	}
	}
	
	return 0;
}