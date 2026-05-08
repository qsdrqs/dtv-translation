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

int main(){
	int i = 0;
	
	scanf("%d",&i);
	
	if(i % 2 == 0){
		printf("%d",((i / 2) - 1));
	}else{
		printf("%d",(((i + 1) / 2) - 1));
	}
	return 0;
}