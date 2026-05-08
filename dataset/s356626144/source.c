#include<stdio.h>
#include<string.h>
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
  char c[3];
  int stock=0;
  int flag=1;
  int n;
  scanf("%d",&n);
  for(;n>0;n--)
    {
      scanf("%s",c);
      if(strcmp(c,"A")==0) stock++;
      if(strcmp(c,"Un")==0)
	{
	  if(stock>0) stock--;
	  else flag=0;
	}
    }
  if((flag==1)&&(stock==0)) printf("YES\n");
  else printf("NO\n");
  return 0;
}