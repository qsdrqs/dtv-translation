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

int main(void){
	int *score;
	int s,i;
	while(scanf("%d", &s) != EOF && s != 0){
		int max=0, min=1000, sum=0, average;
		score = (int *)(malloc(sizeof(int) * s));
		for(i = 0; i < s; i++){
			scanf("%d", (score + i));
			sum = sum + score[i];
			if(score[i] < min){
				min = score[i];
			}
			if(score[i] > max){
				max = score[i];
			}
		}
		sum = sum - (min + max);
		average = sum / (s - 2);
		printf("%d\n", average);
	}
	
	return 0;
}