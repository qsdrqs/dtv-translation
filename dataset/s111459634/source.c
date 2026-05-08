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
	int i, j, n, t, ice[10];
	
	while (scanf("%d", &n), n != 0){
		for (i = 0; i < 10; i++){
			ice[i] = 0;
		}
		
		for (i = 0; i < n; i++){
			scanf("%d", &t);
			ice[t]++;
		}
		
		for (i = 0; i < 10; i++){
			if (ice[i] == 0){
				printf("-\n");
			}
			else {
				for (j = 0; j < ice[i]; j++){
					printf("*");
				}
				puts("");
			}
		}
	}
	
	return (0);
}