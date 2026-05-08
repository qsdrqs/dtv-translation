#include<stdio.h>
#include<stdlib.h>
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define LARGE 101
#define INF 2000000000

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
	int i,j,N,W;
	int sum=0;
	int v[LARGE];
	int w[LARGE];
	int **dp;

	scanf("%d %d",&N,&W);
	
	for(i=1;i<=N;i++){
		scanf("%d %d",&v[i],&w[i]);
		sum+=v[i];
	}
	
	dp=malloc(sizeof(int*)*(N+1));
	for(i=0;i<=N;i++){
		dp[i]=malloc(sizeof(int)*(sum+1));
		for(j=0;j<=sum;j++)dp[i][j]=INF;
	}
	
	
	for(i=0;i<=N;i++)dp[i][0]=0;
	
	for(i=1;i<=N;i++){
		for(j=0;j<=sum;j++){
			if(dp[i-1][j]!=INF){
				dp[i][j]=MIN(dp[i-1][j],dp[i][j]);
				if(dp[i-1][j]+w[i]<=W)dp[i][j+v[i]]=MIN(dp[i][j+v[i]],dp[i-1][j]+w[i]);
			}
		}
	}
	
	for(i=sum;i>=0;i--){
		if(dp[N][i]!=INF){
			printf("%d\n",i);
			break;
		}
	}
	
	return 0;
}
