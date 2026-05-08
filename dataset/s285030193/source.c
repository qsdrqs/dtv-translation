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

int main(void)
{
	int W,H,C,amari,big,small,gcd,tate,yoko;
	scanf("%d %d %d",&W,&H,&C);
	big=W;
	small=H;
	while(big%small!=0){
		amari=big%small;
		big=small;
		small=amari;
	}
	gcd=small;
	yoko=W/gcd;
	tate=H/gcd;
	printf("%d\n",(tate*yoko)*C);
	return 0;
}
	