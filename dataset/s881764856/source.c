#include <stdio.h>
#include <string.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int stack_num[100];
char stack[100][1000];

int main(void) {
	int n;
	char command[8];
	int taisyo1,taisyo2;
	char color[4];
	scanf("%d",&n);
	while(1) {
		scanf("%s",command);
		if(strcmp(command,"push")==0) {
			scanf("%d%s",&taisyo1,color);
			taisyo1--;
			stack[taisyo1][stack_num[taisyo1]++]=color[0];
		} else if(strcmp(command,"pop")==0) {
			scanf("%d",&taisyo1);
			taisyo1--;
			if(stack_num[taisyo1]>0) {
				printf("%c\n",stack[taisyo1][--stack_num[taisyo1]]);
			}
		} else if(strcmp(command,"move")==0) {
			scanf("%d%d",&taisyo1,&taisyo2);
			taisyo1--;taisyo2--;
			if(stack_num[taisyo1]>0) {
				stack[taisyo2][stack_num[taisyo2]++]=
					stack[taisyo1][--stack_num[taisyo1]];
			}
		} else if(strcmp(command,"quit")==0) {
			break;
		}
	}
	return 0;
}