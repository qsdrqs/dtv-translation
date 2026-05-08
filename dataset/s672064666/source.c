/* 
   AOJ 1144
   Curling 2.0

*/

#include<stdio.h>
#define MAXW 20
#define MAXH 20
#define MAX_DEPTH 10

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int w, h;
int ans = 11;
int map[MAXH][MAXW];
int dx[4] = {1, 0, -1, 0};
int dy[4] = {0, 1, 0, -1};


int in(int x, int y)
{
  return 0 <= x && x < w && 0 <= y && y < h;
}


void search(int x, int y, int cnt)
{
  int i, nx, ny;
  if(cnt > MAX_DEPTH)return;

  for(i = 0; i < 4; i++)
    {
      nx = x + dx[i];
      ny = y + dy[i];

      if(!in(nx, ny) || map[ny][nx] == 1)
	continue;

      while(in(nx, ny) && map[ny][nx] == 0 || map[ny][nx] == 2)
	nx += dx[i], ny += dy[i];

      if(!in(nx, ny))
	continue;
	
      if(map[ny][nx] == 3)
	{
	  if(cnt + 1 < ans)
	    ans = cnt + 1;
	  return;
	}

      if(map[ny][nx] == 1)
	{
	  map[ny][nx] = 0;
	  search(nx - dx[i], ny - dy[i], cnt + 1);
	  map[ny][nx] = 1;
	}
    }
}

int main(void)
{
  int i, j, sx, sy;

  while(scanf("%d %d", &w, &h), (w && h))
    {
      for(i = 0; i < h; i++)
	for(j = 0; j < w; j++)
	  {
	    scanf("%d", &map[i][j]);
	    if(map[i][j] == 2)
	      sx = j, sy = i;
	  }
      search(sx, sy, 0);
      printf("%d\n", (ans == 11) ? -1 : ans);
      ans = 11;
    }

  return 0; 
}