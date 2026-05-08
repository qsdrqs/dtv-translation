#include <stdio.h>
#include <stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct {
	long number;
	long x;
  long y;
} S_TOWN;
typedef struct {
	long a;
  long b;
  long cost;
} S_NODE;

int cmpAscX(const void * n1, const void * n2)
{
	if (((S_TOWN *)n1)->x > ((S_TOWN *)n2)->x)
	{
		return 1;
	}
	else if (((S_TOWN *)n1)->x < ((S_TOWN *)n2)->x)
	{
		return -1;
	}
	else
	{
    if (((S_TOWN *)n1)->number > ((S_TOWN *)n2)->number)
  	{
  		return 1;
  	}
  	else if (((S_TOWN *)n1)->number < ((S_TOWN *)n2)->number)
  	{
  		return -1;
  	}
    else
    {
      return 0;
    }
	}
}
int cmpAscY(const void * n1, const void * n2)
{
	if (((S_TOWN *)n1)->y > ((S_TOWN *)n2)->y)
	{
		return 1;
	}
	else if (((S_TOWN *)n1)->y < ((S_TOWN *)n2)->y)
	{
		return -1;
	}
	else
	{
    if (((S_TOWN *)n1)->number > ((S_TOWN *)n2)->number)
  	{
  		return 1;
  	}
  	else if (((S_TOWN *)n1)->number < ((S_TOWN *)n2)->number)
  	{
  		return -1;
  	}
    else
    {
      return 0;
    }
	}
}
int cmpNode(const void * n1, const void * n2)
{
	if (((S_NODE *)n1)->cost > ((S_NODE *)n2)->cost)
	{
		return 1;
	}
	else if (((S_NODE *)n1)->cost < ((S_NODE *)n2)->cost)
	{
		return -1;
	}
	else
	{
    return 0;
	}
}

int main(void) {

  long n;
  scanf("%ld", &n);
  S_TOWN towns[n];
  for (long i = 0; i < n; i++) {
    towns[i].number = i;
    scanf("%ld %ld", &towns[i].x, &towns[i].y);
  }
  S_NODE nodes[n*2-2];
  qsort(towns, n, sizeof(S_TOWN), cmpAscX);
  for (long i = 0; i < n-1; i++) {
    nodes[i].a = towns[i].number;
    nodes[i].b = towns[i+1].number;
    nodes[i].cost = towns[i+1].x-towns[i].x;
  }
  qsort(towns, n, sizeof(S_TOWN), cmpAscY);
  for (long i = 0; i < n-1; i++) {
    nodes[n-1+i].a = towns[i].number;
    nodes[n-1+i].b = towns[i+1].number;
    nodes[n-1+i].cost = towns[i+1].y-towns[i].y;
  }
  qsort(nodes, n*2-2, sizeof(S_NODE), cmpNode);
  long parent[n];
  for (long i = 0; i < n; i++) {
    parent[i] = i;
  }
  long par_a,par_b;
  long list[n];
  long list_size;
  long sum = 0;
  for (long i = 0; i < n*2-2; i++) {
    par_a = nodes[i].a;
    list_size = 0;
    while (parent[par_a] != par_a) {
      list[list_size] = par_a;
      list_size++;
      par_a = parent[par_a];
    }
    for (long j = 0; j < list_size; j++) {
      parent[list[j]] = par_a;
    }
    par_b = nodes[i].b;
    list_size = 0;
    while (parent[par_b] != par_b) {
      list[list_size] = par_b;
      list_size++;
      par_b = parent[par_b];
    }
    for (long j = 0; j < list_size; j++) {
      parent[list[j]] = par_b;
    }
    if (par_a != par_b) {
      parent[par_b] = par_a;
      sum += nodes[i].cost;
    }
  }
  printf("%ld\n", sum);

  return 0;
}