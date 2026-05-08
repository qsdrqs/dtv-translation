#include <stdio.h>
#include <stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int max(int a, int b){
	return a >= b ? a : b;
}

int main(){
	int H, W, N, sr, sc, i, j;
	scanf("%d%d%d", &H, &W, &N);
	scanf("%d%d", &sr, &sc);
	char *S = (char *)malloc(sizeof(char) * (N + 1));
	scanf("%s", S);
	char *T = (char *)malloc(sizeof(char) * (N + 1));
	scanf("%s", T);
	int now, mU = 0;
	for(i = 0, now = 0; i < N; i++){
		if(S[i] == 'U'){
			now++;
		}
		mU = max(mU, now);
		if(T[i] == 'D' && now > sr - H){
			now--;
		}
		mU = max(mU, now);
	}
	if(mU >= sr){
		printf("NO\n");
		return 0;
	}
	mU = 0;
	for(i = 0, now = 0; i < N; i++){
		if(S[i] == 'D'){
			now++;
		}
		mU = max(mU, now);
		if(T[i] == 'U' && now > -sr + 1){
			now--;
		}
		mU = max(mU, now);
	}
	if(mU > H - sr){
		printf("NO\n");
		return 0;
	}
	mU = 0;
	for(i = 0, now = 0; i < N; i++){
		if(S[i] == 'L'){
			now++;
		}
		mU = max(mU, now);
		if(T[i] == 'R' && now > sc - W){
			now--;
		}
		mU = max(mU, now);
	}
	if(mU >= sc){
		printf("NO\n");
		return 0;
	}
	mU = 0;
	for(i = 0, now = 0; i < N; i++){
		if(S[i] == 'R'){
			now++;
		}
		mU = max(mU, now);
		if(T[i] == 'L' && now > -sc + 1){
			now--;
		}
		mU = max(mU, now);
	}
	if(mU > W - sc){
		printf("NO\n");
		return 0;
	}
	printf("YES\n");
	return 0;
}