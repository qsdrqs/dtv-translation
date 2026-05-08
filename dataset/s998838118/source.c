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
	char input[32];
	int count=0;
	int left_end=-1;
	if(scanf("%s",input)!=1)return 1;
	do {
		int add=0,sub=0;
		int i;
		left_end++;
		if(input[left_end]=='0')continue;
		for(i=0;input[i]!='\0';i++) {
			if(i<left_end)sub=sub*10+input[i]-'0';
			else add=add*10+input[i]-'0';
		}
		/*  x-y==sub && x+y==add */
		if((add+sub)%2==0 && (add-sub)>=0 && (add-sub)%2==0)count++;
	} while(input[left_end]!='\0');
	printf("%d\n",count);
	return 0;
}