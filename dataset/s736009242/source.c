#include <stdio.h>
#include <stdbool.h>
#include <string.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

bool wall[10000][10000][4];
char str[10001];

const int U = 0, R = 1, D = 2, L = 3;
char dirchar[] = "URDL";
int righthand(int x) {return (x+1)%4;}
int lefthand(int x) {return (x+3)%4;}
int dx[] = {0, 1, 0, -1};
int dy[] = {-1, 0, 1, 0};

int main() {
  bool firsttime = true;
  int width, height=0;
  int dir = R, x = 0, y = 0, i;

  while (true) {
    scanf("%9999s\n", str);

    if (firsttime) {
      width = strlen(str)+1;
      firsttime = false;
    }

    for (i = 0; i<width; i++)
      wall[i][height][R] = wall[i+1][height][L] = (str[i] == '1');

    if (scanf("%10000s\n", str) == -1)
      break;

    for (i=0; i<width; i++)
      wall[i][height][D] = wall[i][height+1][U] = (str[i] == '1');

    height++;
  }

  firsttime = true;
  while (true) {
    int nextdir;

    if (!firsttime && x == 0 && y == 0)
      break;

    for (nextdir = lefthand(dir); !wall[x][y][nextdir]; nextdir = righthand(nextdir))
      ;

    putchar(dirchar[nextdir]);
    x += dx[nextdir];
    y += dy[nextdir];
    dir = nextdir;
    firsttime = false;
  }

  puts("");
  return 0;
}