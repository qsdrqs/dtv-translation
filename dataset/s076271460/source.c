#include <stdio.h>
#include <string.h>
#define ll long long
#define rep(i,l,r)for(ll i=(l);i<(r);i++)
#define repp(i,l,r,k)for(ll i=(l);i<(r);i+=(k))
#define INF ((1LL<<62)-(1LL<<31))
#define max(p,q)((p)>(q)?(p):(q))
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

int upll(const void*a, const void*b){return*(ll*)a<*(ll*)b?-1:*(ll*)a>*(ll*)b?1:0;}
int downll(const void*a, const void*b){return*(ll*)a<*(ll*)b?1:*(ll*)a>*(ll*)b?-1:0;}
void sortup(ll*a,int n){qsort(a,n,sizeof(ll),upll);}
void sortdown(ll*a,int n){qsort(a,n,sizeof(ll),downll);}

ll x[20],y[20];
ll xx[20],yy[20];

void oresen(ll m,ll*x,ll*y){
	ll prex,prey;
	rep(i,0,m){
		ll tx,ty;
		scanf("%lld%lld",&tx,&ty);
		if(i){
			x[i]=tx-prex;
			y[i]=ty-prey;
		}
		prex=tx;
		prey=ty;
	}
}

int main(){
	ll n;
	while(scanf("%lld",&n),n){
		ll m;
		scanf("%lld",&m);
		oresen(m,x,y);
		rep(i,0,n){
			ll mm;
			scanf("%lld",&mm);
			oresen(mm,xx,yy);
			//(x,y),(-y,x),(-x,-y),(y,-x)
			ll ans=0;
			if(m==mm){
				ll flag;
				flag=1;rep(i,1,m)flag&=(x[i]==xx[i])&&(y[i]==yy[i]);ans|=flag;
				flag=1;rep(i,1,m)flag&=(x[i]==-yy[i])&&(y[i]==xx[i]);ans|=flag;
				flag=1;rep(i,1,m)flag&=(x[i]==-xx[i])&&(y[i]==-yy[i]);ans|=flag;
				flag=1;rep(i,1,m)flag&=(x[i]==yy[i])&&(y[i]==-xx[i]);ans|=flag;
				flag=1;rep(i,1,m)flag&=(-x[i]==xx[m-i])&&(-y[i]==yy[m-i]);ans|=flag;
				flag=1;rep(i,1,m)flag&=(-x[i]==-yy[m-i])&&(-y[i]==xx[m-i]);ans|=flag;
				flag=1;rep(i,1,m)flag&=(-x[i]==-xx[m-i])&&(-y[i]==-yy[m-i]);ans|=flag;
				flag=1;rep(i,1,m)flag&=(-x[i]==yy[m-i])&&(-y[i]==-xx[m-i]);ans|=flag;
				//rep(i,1,m)printf("%lld %lld %lld %lld\n",x[i],y[i],xx[i],yy[i]);
			}
			if(ans)printf("%lld\n",i+1);
		}
		puts("+++++");
	}
	return 0;
}
