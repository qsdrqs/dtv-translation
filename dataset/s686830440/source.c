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
  int n,i,j,w,r[300],d[300][2];
  while(scanf("%d",&n),n){
    for(i=0;i<n*2;i+=2){
      scanf("%d %d %d",&w,&d[i][0],&d[i+1][0]);
      d[i  ][1]=w;
      d[i+1][1]=-w;
    }
    d[r[i]=i][0]=2200000000;
    for(i=0;i<n*2;i++){
      r[i]=i;
      for(j=i;j;j--){
	if(d[r[j-1]][0]>d[r[j]][0]){
	  w=r[j-1];
	  r[j-1]=r[j];
	  r[j]=w;
	}
      }
    }
    for(i=w=0;i<n*2;i++){//printf("%d ",d[r[i]][0]);
      while(d[r[i]][0]==d[r[i+1]][0])w+=d[r[i++]][1];
      w+=d[r[i]][1];//printf("%d ",w);
      if(w>150)break;
    }
    if(n*2-i)printf("NG\n");
    else     printf("OK\n");//*/
  }
  return 0;
}