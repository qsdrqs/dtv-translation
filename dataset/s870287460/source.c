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

int pushBack(int A[],int x,int tail)
{
  A[tail]=x;
  tail++;
  return tail;
}
void randomAccess(int A[],int p)
{
  printf("%d\n",A[p]);
}
int popBack(int tail)
{
  return tail-1;
}
int main(void)
{
  int p,q,i,ord,x,A[200000],tail=0;
  scanf("%d",&q);
  for(i=0;i<q;i++)
  {
    scanf("%d",&ord);
    if(ord==0)
    {
      scanf("%d",&x);
      tail=pushBack(A,x,tail);
    }
    else if(ord==1)
    {
      scanf("%d",&p);
      randomAccess(A,p);
    }
    else if(ord==2)
    {
      tail=popBack(tail);
    }
  }
  return 0;
}

