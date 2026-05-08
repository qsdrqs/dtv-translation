#include<stdio.h>
#include<string.h>
#define ll long long
#define MOD 1000000007
#define add0(p,q)(p=(p+(q))%MOD)
#define add1(p,q)(p=(p+(q)-1)%MOD+1)

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

ll dp[200010][2];//dp[i][j]=下からi桁見て小さいことが確定してい(j?る:ない)ものの和
ll cnt[200010][2];//dp[i][j]=下からi桁見て小さいことが確定してい(j?る:ない)ものの個数
char s[200010],t[200010];
int main(){
	scanf("%s%s",s,t);
	int n=strlen(s);
	ll p10=1;
	cnt[n][1]=1;
	for(int i=n-1;i>=0;i--){
		if(t[i]=='?'){
			for(int k=0;k<10;k++){
				add0(dp [i][k< s[i]-'0'],dp[i+1][0]+k*p10*cnt[i+1][0]);
				add1(cnt[i][k< s[i]-'0'],cnt[i+1][0]);
				add0(dp [i][k<=s[i]-'0'],dp[i+1][1]+k*p10*cnt[i+1][1]);
				add1(cnt[i][k<=s[i]-'0'],cnt[i+1][1]);
			}
		}else{
			int k=t[i]-'0';
			add0(dp [i][k< s[i]-'0'],dp[i+1][0]+k*p10*cnt[i+1][0]);
			add1(cnt[i][k< s[i]-'0'],cnt[i+1][0]);
			add0(dp [i][k<=s[i]-'0'],dp[i+1][1]+k*p10*cnt[i+1][1]);
			add1(cnt[i][k<=s[i]-'0'],cnt[i+1][1]);
		}
		p10=p10*10%MOD;
	}
	printf("%d\n",dp[0][1]);
}
