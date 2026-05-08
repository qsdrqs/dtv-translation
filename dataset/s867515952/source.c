#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define UP 0//North
#define DOWN 1//South
#define RIGHT 2//East
#define LEFT 3//West

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int Direct(int s){
	if((s>=65) && (s<=77)){
		return UP;
	}
	if((s>=78) && (s<=90)){
		return DOWN;
	}
	if((s>=97) && (s<=109)){
		return RIGHT;
	}
	return LEFT;
}

void calc(int N,char *S){
	int x=0,y=0;
	int d;

	for(int i=0;i<N;i++){
		d=Direct(S[i]);
		if(d==UP){
			y--;
		}
		if(d==DOWN){
			y++;
		}
		if(d==RIGHT){
			x++;
		}
		if(d==LEFT){
			x--;
		}
	}

	printf("%d\n",(abs(x)+abs(y)));

	d=0;
	if(x>0){
		for(int i=0;i<x;i++){
			printf("a");
		}
	}else{
		x*=-1;
		for(int i=0;i<x;i++){
			printf("n");
		}
	}
	if(y>0){
		for(int i=0;i<y;i++){
			printf("N");
		}
	}else{
		y*=-1;
		for(int i=0;i<y;i++){
			printf("A");
		}
	}
	printf("\n");
}

int main(){
	int N;
	char *S;

	scanf("%d",&N);
	S=(char*)malloc(sizeof(char)*N);


	scanf("%s",S);

	calc(N,S);


	return 0;
}
