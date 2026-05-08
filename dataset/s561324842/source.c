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

int func(int,int);
int main()
{
  int a,b;
  while(scanf("%d%d",&a,&b)!=EOF) printf("%d\n",func(a,b));
  return 0;
}
int func(int a,int b)
{
  int rep;
  while(a%b!=0)
    {
      rep=a%b;
      a=b;
      b=rep;
    }
  return b;
}