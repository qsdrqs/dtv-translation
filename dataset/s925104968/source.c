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

int parent(int i)
{
  return i / 2;
}

int left(int i)
{
  return 2 * i;
}

int right(int i)
{
  return 2 * i + 1;
}

int main()
{
  int H,i,A[255];

  scanf("%d",&H);

  for(i = 1;i <= H;i++)
    {
      scanf("%d",&A[i]);
    }
  for(i = 1;i <= H;i++)
    {
      printf("node %d: key = %d, ",i,A[i]);

      if(parent(i) >= 1) printf("parent key = %d, ",A[parent(i)]);
      if(left(i) <= H) printf("left key = %d, ",A[left(i)]);
      if(right(i) <= H) printf("right key = %d, ",A[right(i)]);
      printf("\n");
    }
  return 0;
}

