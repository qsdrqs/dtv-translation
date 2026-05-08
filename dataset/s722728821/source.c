#include<stdio.h>
#include<string.h>
#define Max(x,y) ((x>y)?x:y)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int c[10005],d[10005];
int func(int s,int t){
	int x=0;
	while(c[s]==c[t] && d[s]+d[t]>=4){
		x+=d[s]+d[t];
		s=s-d[s];
		t=t+d[t];
	}
	//printf(" %d %d\n",s,t);
	return x;
}
int main(){
	int i,j,n,x,y,s,t,ans;
	while(1){
		scanf("%d",&n);
		if(n==0)break;
		c[0]=5;c[n+1]=6;
		d[0]=d[n+1]=0;
		scanf("%d",&c[1]);
		x=c[1];y=1;
		for(i=2;i<=n+1;i++){
			if(i<n+1)scanf("%d",&c[i]);
			if(c[i]!=x){
				for(j=1;j<=y;j++)
					d[i-j]=y;
				y=1;
				x=c[i];
			}else y++;
		}
		//for(i=1;i<=n;i++)printf("%d ",d[i]);
		//printf("\n");
		ans=0;
		for(i=1;i<=n;i++){
			if(c[i-1]==c[i+1]){
				if(c[i-1]!=c[i] && d[i-1]+d[i+1]>=3){
					s=(i-1)-d[i-1];
					t=(i+1)+d[i+1];
					ans=Max(ans,d[i-1]+d[i+1]+1+func(s,t));
					//printf("%d:%d\n",i,d[i-1]+d[i+1]+1+func(s,t));
				}
			}else{
				if(c[i-1]!=c[i] && d[i-1]>=3){
					s=(i-1)-d[i-1];
					if(c[i]==c[i+1])t=i,x=0;
					else t=i+1,x=1;
					ans=Max(ans,d[i-1]+x+func(s,t));
					//printf("%d:%d\n",i,d[i-1]+1+func(s,t));
				}
				if(c[i+1]!=c[i] && d[i+1]>=3){
					t=(i+1)+d[i+1];
					if(c[i]==c[i-1])s=i,x=0;
					else s=i-1,x=1;
					ans=Max(ans,d[i+1]+x+func(s,t));
					//printf("%d:%d\n",i,d[i+1]+1+func(s,t));
				}
			}
		}
		printf("%d\n",n-ans);
	}
	return 0;
}