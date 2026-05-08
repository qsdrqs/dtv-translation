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
#define MOD 998244353
//#define MOD 1000000007
#define invp(a,p)pom(a,p-2,p)

int*makeSA(char*s,int len){
	len++;
	int*SAidx=calloc(len,sizeof(int));
	int*ord=calloc(len,sizeof(int));
	//1文字目
	int cnt1[256]={},cnt2[256]={};
	for(int i=0;i<len;i++)cnt1[s[i]+1]++,cnt2[s[i]+1]|=1;
	for(int i=1;i<256;i++)cnt1[i]+=cnt1[i-1],cnt2[i]+=cnt2[i-1];
	for(int i=0;i<len;i++)SAidx[cnt1[s[i]]++]=i,ord[i]=cnt2[s[i]];
	
	int*cnt=calloc(len+1,sizeof(int));
	int*idx2=calloc(len,sizeof(int));
	int*temp=calloc(len,sizeof(int));
	for(int k=1;k<len;k*=2){
		//2*k文字まで見る
		for(int i=0;i<len;i++)cnt[i]=0;
		for(int i=0;i<len;i++)cnt[ord[i]+1]++;
		for(int i=1;i<len;i++)cnt[i]+=cnt[i-1];
		for(int i=0;i<len;i++)idx2[cnt[ord[(SAidx[i]-k+len)%len]]++]=(SAidx[i]-k+len)%len;
		temp[idx2[0]]=0;
		for(int i=1;i<len;i++)temp[idx2[i]]=temp[idx2[i-1]]+(ord[idx2[i-1]]!=ord[idx2[i]]||ord[(idx2[i-1]+k)%len]!=ord[(idx2[i]+k)%len]);
		for(int i=0;i<len;i++)ord[i]=temp[i],SAidx[i]=idx2[i];
	}
	free(temp);
	free(idx2);
	free(cnt);
	free(ord);
	return SAidx+1;
}

char t[10010];
char s[10010];
int main(){
	int n,k;
	scanf("%d%d%s",&n,&k,t);
	if(k>15)k=15;
	rep(i,0,n)s[i]=t[n-1-i];

	while(k--){
		rep(i,0,n)t[i]=s[n-1-i];
		rep(i,0,n)t[n+i]=s[i];
		int*p=makeSA(t,2*n);
		int mi=0;
		while(p[mi]>=n)mi++;
//		rep(i,0,2*n)printf("%d ",p[i]);puts("");
		rep(i,0,n)s[i]=t[p[mi]+i];
	}
	puts(s);
}