#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>

#define P 1000000007

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int comp(const void *a, const void *b){return *(int*)a-*(int*)b;}

int main(void){
	int n, i;
	char s[101];
	scanf("%d%s", &n, s);
	int a=0, b=0, c=0;
	for(i=0; i<n; i++){
		if(s[i]=='('){
			a++;
		}else{
			b++;
			if(a<b){c++; a++;}
		}
	}
	while(c--) putchar('(');
	fputs(s, stdout);
	c=a-b;
	while(c--) putchar(')');
	putchar(10);
}
