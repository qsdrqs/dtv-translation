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

int n;
char expressions[100][200];
int expressions_len[100];
int expression_number[100];
char input[500];
int input_len;

int memo_number[200];

int tansaku_number(int pos) {
	int i;
	int max=-0x10000000;
	int now;
	if(pos>=input_len)return 0;
	if(memo_number[pos]>0)return memo_number[pos]-1;
	for(i=0;i<n;i++) {
		if(strncmp(&input[pos],expressions[i],expressions_len[i])==0) {
			now=tansaku_number(pos+expressions_len[i]);
			now+=expression_number[i];
			if(now>max)max=now;
		}
	}
	memo_number[pos]=max+1;
	return max;
}

int memo_expression[2100];

int tansaku_expression(int rest) {
	int i;
	int result=0x10000000;
	int now;
	if(rest<0)return result;
	if(rest==0)return 0;
	if(memo_expression[rest]>0)return memo_expression[rest]-1;
	for(i=0;i<n;i++) {
		now=tansaku_expression(rest-expression_number[i]);
		now+=expressions_len[i];
		if(now<result)result=now;
	}
	memo_expression[rest]=result+1;
	return result;
}

int main(void) {
	int dataset_count;
	int i;
	int number;
	for(dataset_count=1;;dataset_count++) {
		scanf("%d",&n);
		if(n==0)break;
		for(i=0;i<n;i++) {
			scanf("%s%d",expressions[i],&expression_number[i]);
			expressions_len[i]=strlen(expressions[i]);
		}
		scanf("%s",input);
		input_len=strlen(input);
		memset(memo_number,0,sizeof(memo_number));
		memset(memo_expression,0,sizeof(memo_expression));
		number=tansaku_number(0);
		printf("Case %d: %d\n",dataset_count,tansaku_expression(number));
	}
	return 0;
}