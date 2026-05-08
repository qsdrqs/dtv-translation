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

int tree[262145];
int leaves;

int leftBound(int i) {
  while (i < leaves)
    i *= 2;
  return i - leaves;
}

int rightBound(int i) {
  while (i < leaves)
    i = i * 2 + 1;
  return i - leaves;
}

void add(int cur, int left, int right, int val) {
  int leftB  = leftBound(cur);
  int rightB = rightBound(cur);

  if (leftB == left && rightB == right) {
    tree[cur] += val;
    return;
  }

  if (right <= rightBound(cur * 2))
    add(cur * 2, left, right, val);
  else if (left >= leftBound(cur * 2 + 1))
    add(cur * 2 + 1, left, right, val);
  else {
    add(cur * 2, left, rightBound(2 * cur), val);
    add(cur * 2 + 1, leftBound(cur * 2 + 1), right, val);
  }
}

void print(int i) {
  int cur = leaves + i;
  int ans = tree[cur];

  while (cur != 1) {
    cur /= 2;
    ans += tree[cur];
  }

  printf("%d\n", ans);
}

int main() {
  int n, q, i, command, x, y, z;

  scanf("%d %d", &n, &q);
  
  for (leaves = 1; leaves < n; leaves *= 2);

  //  printf("n: %d, q: %d, leaves: %d\n", n, q, leaves);

  memset(tree, 0, sizeof(tree));

  for (i = 0; i < q; i++) {
    scanf("%d", &command);

    if (command) {
      scanf("%d", &x);
      //  printf("performing print on %d\n", x);
      print(x - 1);
    } else {
      scanf("%d %d %d", &x, &y, &z);
      //printf("performing add on %d, %d, %d\n", x, y, z);
      add(1, x - 1, y - 1, z);
    }
  }
}

