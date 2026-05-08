#include <stdio.h>
#include <stdlib.h>
#define ll long long
#define rep(i,l,r)for(ll i=(l);i<(r);i++)


//行列累乗
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

void matpom(ll*mat,int size,ll n,int m){
	ll*temp=(ll*)malloc(size*size*sizeof(ll));
	ll*ans=(ll*)malloc(size*size*sizeof(ll));

	rep(i,0,size)rep(j,0,size)ans[i*size+j]=i==j;
	while(n){
		if(n%2){
			rep(i,0,size*size)temp[i]=0;
			rep(i,0,size)rep(j,0,size)rep(k,0,size)temp[i*size+j]=(temp[i*size+j]+ans[i*size+k]*mat[k*size+j])%m;
			rep(i,0,size*size)ans[i]=temp[i];
		}
		rep(i,0,size*size)temp[i]=0;
		rep(i,0,size)rep(j,0,size)rep(k,0,size)temp[i*size+j]=(temp[i*size+j]+mat[i*size+k]*mat[k*size+j])%m;
		rep(i,0,size*size)mat[i]=temp[i];
		n/=2;
	}
	rep(i,0,size*size)mat[i]=ans[i];

	free(temp);
	free(ans);
}

ll d[100][100];
int main(){
	int v,e;
	scanf("%d%d",&v,&e);
	while(e--){
		int s,t;
		scanf("%d%d",&s,&t);
		d[s][t]=1;
	}
	
	matpom((ll*)d,100,110,(1<<30)-1);
	rep(i,0,v)rep(j,0,v)if(d[i][j]){
		puts("1");
		return 0;
	}
	puts("0");
}

