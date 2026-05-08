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
	int H, W;
	int i, j;
	
	scanf("%d %d", &H, &W);
	
	while (H != 0 || W != 0){
		for (i = 0; i < H; i++){
			for (j = 0; j < W; j++){
				if (i == 0 || i == H - 1){
					printf("#");
				}
				else if (j == 0 || j == W - 1){
					printf("#");
				}
				else {
					printf(".");
				}
			}
			puts("");
		}
		puts("");
		scanf("%d %d", &H, &W);
	}
	
	return (0);
}