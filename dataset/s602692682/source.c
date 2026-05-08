#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
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


//セグ木ここから
//*
//↓ここを変える
typedef struct atai{ll a,b;}atai;
atai xx(atai x,atai y){
	atai r;
	r.a=min(x.a,y.a);
	r.b=max(x.b,y.b);
	return r;
}
atai aid={INF,-1};
//↑ここを変える

int segNUM;
atai *segN,*seg;
void seguse(int n){
	segN=(atai*)calloc(2*n,sizeof(atai));
	segNUM=n;
	seg=segN+segNUM;
	rep(i,1,2*segNUM)segN[i]=aid;
}
//seg[]に値を与えてから初期化
void seginit(){for(int node=segNUM-1;node;node--)segN[node]=xx(segN[node*2],segN[node*2+1]);}
void segupdate(int node,atai x){
	//seg[node]をxに更新
	node+=segNUM;
	segN[node]=x;
	while(node/=2)segN[node]=xx(segN[node*2],segN[node*2+1]);
}

atai segcalcsub(int l,int r,int k,int cl,int cr){
	if(l>=r)return aid;
	//完全に含むとき
	if(l<=cl&&cr<=r)return segN[k];

	int cm=(cl+cr)/2;
	//左側だけ
	if(r<=cm)return segcalcsub(l,r,2*k  ,cl,cm);
	//右側だけ
	if(cm<=l)return segcalcsub(l,r,2*k+1,cm,cr);
	//両方
	return xx(segcalcsub(l,r,2*k,cl,cm),segcalcsub(l,r,2*k+1,cm,cr));
}
atai segcalc(int l,int r){return segcalcsub(l,r,1,0,segNUM);}
//セグ木ここまで
//*/

int main(){
	seguse(1<<18);
	int n,k;
	scanf("%d%d",&n,&k);
	rep(i,0,n){
		int t;
		scanf("%d",&t);
		seg[i].a=t;
		seg[i].b=t;
	}
	seginit();
	int ans=1;
	rep(i,1,n-k+1){
		ans++;
		if(segcalc(i-1,i-1+k).a==seg[i-1].a && segcalc(i,i+k).b==seg[i+k-1].b)ans--;
	}
	
	int cnt=0,crr=1e9,flag=0;
	rep(i,0,n){
		if(seg[i].a>crr)cnt++;
		else cnt=1;
		crr=seg[i].a;
		if(cnt==k)ans-=!!flag++;
	}
	
	printf("%d",ans);
	
}