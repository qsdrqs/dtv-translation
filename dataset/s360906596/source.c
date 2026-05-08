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

char opera(int i, int j, char array[100][100]);

int main(void)
{
	char array[100][100];
	int i, j;
	char ans;
	int flog;
	
	while (scanf("%s", array[0]) != EOF){
		flog = 0;
		
		for (i = 1; i < 8; i++){
			scanf("%s", array[i]);
		}
		for (i = 0; i < 8; i++){
			for (j = 0; j < 8; j++){
				if (array[i][j] == '1'){
					ans = opera(i, j, array);
					flog++;
					break;
				}
			}
			if (flog != 0){
				break;
			}
		}
		printf("%c\n", ans);
	}
	
	return (0);
}
char opera (int i, int j, char array[100][100])
{
	int line = 0;
	int row  = 0;
	int obli = 0;
	
	if (array[i][j + 1] 	== '1'){
		line++;
		if (array[i][j + 2]	== '1'){
			return ('C');
		}
	}
	if (array[i + 1][j] 	== '1'){
		row++;
		if (array[i + 2][j] == '1'){
			return ('B');
		}
	}
	if (array[i + 1][j + 1] == '1'){
		obli++;
	}
	
	if (line >= 1){
		if (row >= 1){
			if (obli >= 1){
				return ('A');
			}
			return ('G');
		}
		return ('E');
	}
	
	if (row >= 1){
		if (obli >= 1){
			return ('F');
		}
		return ('D');
	}
	
}