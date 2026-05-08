#include <stdio.h>
#include <stdlib.h>
#define min(p,q)((p)<(q)?(p):(q))

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

long v[60],w[60],c[60],u[60],dp[2600];
int main(){
	long n,m;
	scanf("%ld%ld",&n,&m);
	for(int i=0;i<n;i++)scanf("%ld%ld%ld",v+i,w+i,c+i);
	//効率降順
	for(int i=n-1;i>=0;i--)for(int j=0;j<i;j++){
		if(v[j]*w[j+1]<v[j+1]*w[j]){
			long t;
			t=v[j];v[j]=v[j+1];v[j+1]=t;
			t=w[j];w[j]=w[j+1];w[j+1]=t;
			t=c[j];c[j]=c[j+1];c[j+1]=t;
		}
	}
	long ans=0;
	for(int i=0;i<n;i++){
		u[i]=min(c[i],m/w[i]);
		ans+=v[i]*u[i];
		m-=w[i]*u[i];
	}
	long back=min(2500,ans);
	for(int i=n-1;back>0;){
		if(u[i]){
			back-=v[i];
			ans-=v[i];
			m+=w[i];
			u[i]--;
		}else i--;
	}
	for(int i=1;i<2600;i++)dp[i]=1e10;
	for(int i=0;i<n;i++){
		c[i]=min(c[i]-u[i],2600);
		for(int k=1;c[i];k*=2){
			c[i]-=k=min(k,c[i]);
			long vv=v[i]*k,ww=w[i]*k;
			for(int j=2550-vv;j>=0;j--)dp[j+vv]=min(dp[j+vv],dp[j]+ww);
		}
	}
	for(int i=2550;i>=0;i--)if(dp[i]<=m){
		printf("%ld\n",ans+i);
		return 0;
	}
}
