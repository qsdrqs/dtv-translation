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

int main(void)
{
	int a,b,c;
	scanf("%d %d",&a,&b);
	if(a>b){
	c=a-b;
	printf("%d\n",c);
	}
	else {
	c=b-a;
	printf("%d\n",c);
	}
	return 0;
}
	
