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

int main(void)
{
  int N,W,i,j;
  scanf("%d%d",&N,&W);
  int v[N],w[N];
  for(i=0;i<N;i++){
    scanf("%d%d",&v[i],&w[i]);
  }
  int Nap[W+1][N];
  for(i=0;i<=W;i++){
    Nap[i][0]=v[0]*(i/w[0]);
    //printf("%d ",Nap[i][0]);
  }
  for(j=1;j<N;j++){
    for(i=0;i<=W;i++){
      int x=0,y=0,z=0,max;
      x=Nap[i][j-1];
      if(i-w[j]>=0) y=Nap[i-w[j]][j-1]+v[j];
      if(i-w[j]>=0) z=Nap[i-w[j]][j]+v[j];
      if(x>y) max=x;
      else max=y;
      if(max<z) max=z;
      Nap[i][j]=max;
    }
  }
 /*for(j=0;j<N;j++){
    for(i=0;i<=W;i++){
      printf("%d ",Nap[i][j]);
    }
    printf("\n");
  }*/
   printf("%d\n",Nap[W][N-1]);
  return 0;
}

