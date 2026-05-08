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

int main()
{
  int w,h,n;

  scanf("%d %d %d",&w,&h,&n);

  int t[101][101]={};
  int x,y,a;
  int i,j,k;
  int ans=0;

  for (k=1;k<=n;k++) {
    scanf("%d %d %d",&x,&y,&a);
    if (a==1) {
      for (i=0;i<x;i++) {
	for (j=0;j<h;j++) {
	  t[i][j]=1;
	}
      }
    } else if (a==2) {
      for (i=x;i<w;i++) {
	for (j=0;j<h;j++) {
	  t[i][j]=1;
	}
      }
    } else if (a==3) {
      for (i=0;i<w;i++) {
	for (j=0;j<y;j++) {
	  t[i][j]=1;
	}
      }
    } else {
      for (i=0;i<w;i++) {
	for (j=y;j<h;j++) {
	  t[i][j]=1;
	}
      }
    }
  }

  for (i=0;i<w;i++) {
    for (j=0;j<h;j++) {
      if (t[i][j]==0) {
	ans++;
      }
    }
  }

  printf("%d\n",ans);

  return 0;
}