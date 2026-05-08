#include<stdio.h>
#define ll long long
#define rep(i,l,r)for(ll i=(l);i<(r);i++)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

ll pom(ll a,ll n,int m){ll x=1;for(a%=m;n;n/=2)n&1?x=x*a%m:0,a=a*a%m;return x;}
ll gcd(ll p,ll q){for(ll t;q;)t=p%q,p=q,q=t;return p;}

int d[50],cnt;
void f(ll x){
	for(ll p=2;p*p<=x;p++)if(x%p==0){
		d[cnt++]=p;
		while(x%p==0)x/=p;
	}
	if(x!=1)d[cnt++]=x;
}

int ord(ll x,int MOD){
	int e=MOD-1;
	rep(i,0,cnt)while(e%d[i]==0&&pom(x,e/d[i],MOD)==1)e/=d[i];
	return e;
}

int main(){
	int MOD,t;
	scanf("%d%d",&MOD,&t);
	f(MOD-1);
	while(t--){
		int n;
		scanf("%d",&n);
		ll ddd=MOD-1;
		rep(i,0,n){
			int x;
			scanf("%d",&x);
			if(x!=1)ddd=gcd(ddd,(MOD-1)/ord(x,MOD));
		}
		int target;
		scanf("%d",&target);
		int e=(MOD-1)/ord(target,MOD);
		puts(e%ddd?"0":"1");
	}
}
