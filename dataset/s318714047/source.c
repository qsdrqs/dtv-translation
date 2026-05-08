#include<stdio.h>

#define min(a,b) ((a)<(b)?(a):(b))
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

int n;
long long dis[500][500];
long long lis[500][500];

void warshall_floyd(){
	int i,j,k;
	for(k=0;k<n;k++){
		for(i=0;i<n;i++){
			for(j=0;j<n;j++){
				dis[i][j]=min(dis[i][j],dis[i][k]+dis[k][j]);
			}
		}
	}
}

void warshall_floydd(){
	int i,j,k;
	for(k=0;k<n;k++){
		for(i=0;i<n;i++){
			for(j=0;j<n;j++){
				lis[i][j]=min(lis[i][j],lis[i][k]+lis[k][j]);
			}
		}
	}
}

int main(){
	int m,i,j,k,l;
	for(i=0;i<500;i++){
		for(j=0;j<500;j++){
			dis[i][j]=INF;
		}
	}
	scanf("%d%d%d",&n,&m,&l);
	for(i=0;i<m;i++){
		int a,b,c;
		scanf("%d%d%d",&a,&b,&c);
		a--,b--;
		dis[a][b]=c;
		dis[b][a]=c;
	}
	warshall_floyd();
	for(i=0;i<500;i++){
		for(j=0;j<500;j++){
			lis[i][j]=INF;
		}
	}
	for(i=0;i<500;i++){
		for(j=0;j<500;j++){
			if(dis[i][j]<=l){
				lis[i][j]=1;
			}
		}
	}
	warshall_floydd();
	int q;
	scanf("%d",&q);
	for(i=0;i<q;i++){
		int s,t;
		scanf("%d%d",&s,&t);
		s--,t--;
		if(lis[s][t]<INF)printf("%lld\n",lis[s][t]-1);
		else puts("-1");
	}
	return 0;
}