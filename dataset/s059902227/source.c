#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ll long long
#define rep(i,l,r)for(ll i=(l);i<(r);i++)
#define repp(i,l,r,k)for(ll i=(l);i<(r);i+=(k))
#define INF ((1LL<<62)-(1LL<<31))
#define max(p,q)((p)>(q)?(p):(q))
#define min(p,q)((p)<(q)?(p):(q))
#define bit(n,m)(((n)>>(m))&1)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int upll(const void*a, const void*b){return*(ll*)a<*(ll*)b?-1:*(ll*)a>*(ll*)b?1:0;}
int downll(const void*a, const void*b){return*(ll*)a<*(ll*)b?1:*(ll*)a>*(ll*)b?-1:0;}
void sortup(ll*a,int n){qsort(a,n,sizeof(ll),upll);}
void sortdown(ll*a,int n){qsort(a,n,sizeof(ll),downll);}
ll pom(ll a,ll n,int m){ll x=1;for(a%=m;n;n/=2)n&1?x=x*a%m:0,a=a*a%m;return x;}
//#define MOD 998244353
#define MOD 1000000007
#define invp(a,p)pom(a,p-2,p)

ll n;
ll a[200010];
ll dp[200010][6];
int main(){
	scanf("%lld",&n);
	rep(i,0,n)scanf("%lld",a+i);
	rep(i,0,n){
		dp[i+1][0]=a[i]              +dp[i][0];
		dp[i+1][1]=(a[i]==0?2:a[i]%2)+min(dp[i][0],dp[i][1]);
		dp[i+1][2]=(a[i]+1)%2        +min(dp[i][0],min(dp[i][1],dp[i][2]));
		dp[i+1][3]=(a[i]==0?2:a[i]%2)+min(dp[i][0],min(dp[i][1],min(dp[i][2],dp[i][3])));
		dp[i+1][4]=a[i]              +min(dp[i][0],min(dp[i][1],min(dp[i][2],min(dp[i][3],dp[i][4]))));
		rep(j,0,5)dp[i+1][j]=min(dp[i+1][j],INF);
	}
	printf("%lld",min(dp[n][0],min(dp[n][1],min(dp[n][2],min(dp[n][3],dp[n][4])))));
}