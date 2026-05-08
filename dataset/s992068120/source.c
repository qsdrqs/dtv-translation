#include<stdio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main(){
	int y[2],m[2],d[2],n[]={0,31,28,31,30,31,30,31,31,30,31,30,31},ans,i;
	while(scanf("%d%d%d%d%d%d",&y[0],&m[0],&d[0],&y[1],&m[1],&d[1])!=EOF){
		if(y[0]<0 || y[1]<0 || m[0]<0 || m[1]<0 || d[0]<0 || d[1]<0)break;
		ans=0;
		if(y[0]==y[1]){
			if(m[0]==m[1]){
				ans=d[1]-d[0];
			}else{
				ans=n[m[0]]-d[0]+1+d[1]-1;
				for(i=m[0]+1;i<m[1];i++)ans+=n[i];
			}
		}else{
			ans+=n[m[0]]-d[0]+1;
			for(i=m[0]+1;i<=12;i++)ans+=n[i];
			ans+=d[1]-1;
			for(i=1;i<m[1];i++)ans+=n[i];
			
			if(y[1]-y[0]>1)ans+=((y[1]-1)-(y[0]))*365;
			for(i=y[0]+1;i<y[1];i++)if((i%4==0 && i%100!=0) || i%400==0)ans++;
			
			if(m[0]==1 || (m[0]==2 && d[0]==29))
				if((y[0]%4==0 && y[0]%100!=0) || y[0]%400==0)ans++;
			if(m[1]>2 || (m[1]==2 && d[1]==29))
				if((y[1]%4==0 && y[1]%100!=0) || y[1]%400==0)ans++;
		}
		printf("%d\n",ans);
	}
	return 0;
}