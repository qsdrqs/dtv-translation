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

int main (void){
	int D;
	scanf("%d",&D);
	if (D==25) printf("Christmas");
	 else if (D==24) printf("Christmas Eve");
		else if (D==23) printf("Christmas Eve Eve");
			else if (D==22) printf("Christmas Eve Eve Eve");
				else return 0;
	return 0;
	
}