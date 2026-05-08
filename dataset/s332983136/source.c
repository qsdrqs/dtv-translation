#include <stdio.h>

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
int t[52][52];
int dx[] = {-1, 0, 1, -1, 1, -1, 0, 1};
int dy[] = {-1, -1, -1, 0, 0, 1, 1, 1};

void solve(int x, int y){
  int i;
  int nx, ny;

  t[y][x] = 0;

  for(i = 0; i < 8; i++){
    nx = x + dx[i];
    ny = y + dy[i];

    if(nx < 0 || w <= nx || ny < 0 || h <= ny || t[ny][nx] == 0) continue;

    solve(nx, ny);
  }
}

int main(void){
  int i, j;
  int ans = 0;

  while(scanf("%d %d", &w, &h), w || h){
    for(i = 0; i < h; i++){
      for(j = 0; j < w; j++){
        scanf("%d", &t[i][j]);
      }
    }

    ans = 0;

    for(i = 0; i < h; i++){
      for(j = 0; j < w; j++){
        if(t[i][j] == 1){
          solve(j, i);
          ans++;
        }
      }
    }

    printf("%d\n", ans);
  }

  return 0;
}