#include<stdio.h>
#include<string.h>

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
	int l;
	char s[131072];
	scanf("%s",s);
	l = strlen(s);
	if(s[0] == s[l-1]){l++;}
	if(l%2){printf("First\n");}else{printf("Second\n");}
	return 0;
}