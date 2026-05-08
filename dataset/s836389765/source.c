/*
  filename:A2912.c
*/
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

int p[10],e[10];
int nc3table[]={1,4,10,20,35,56,84,120,165,220,286,364};

int factorize(int v)
{
  int a=v,i,j,k;
  k=0;
  for(j=2; j<=v/2 && 1<a; j+=1+(j&1))
    {for(i=0;a%j==0;i++)
	a/=j;
      if(i)
	{ p[k]=j;
	  e[k]=i;
	  k++;
	}
    }
  return k;
}

int main()
{
  int i,n,n2,c,ret;

  scanf("%d",&n);
  c=factorize(n);
  //for(i=0;i<c;i++)
  //  printf("%d^%d\n",p[i],e[i]);
  
  if(c==0)
    { 
    if(n==1)
      ret=1;
    else
      ret=4;
    }
  else if(p[0]==2)
    {
      ret = e[0]+1;
      for(i=1;i<c;i++)
	ret *= nc3table[e[i]];
    }
  else
    {
      ret=1; 
      for(i=0;i<c;i++) 
	ret *= nc3table[e[i]];
    }  
  printf("%d\n",ret);
  return 0;
}

