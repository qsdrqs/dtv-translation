#include <stdio.h>

#define XLEN_MAX 1000

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

char x[XLEN_MAX + 1];

int solve(void){
	int a,b;
	char *s;
	a = b = 0;
	s = x;
	while(*s){
		b += (int)(*s - '0');
		s++;
		a ^= 1;
	}
	if((((b - 1) / 9) & 1) ^ a){
		puts("Audrey wins.");
	}else{
		puts("Fabre wins.");
	}
	return 0;
}

int main(void){
	int i;
	int n;
	scanf("%d", &n);
	i = n;
	while(n--){
		scanf("%s", x);
		solve();
	}
	return 0;
}