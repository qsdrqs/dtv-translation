#include <stdio.h>
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

int main(void) {

  char s[51];
  scanf("%s", s);
  char akiba[10] = "AKIHABARA";
  int current = 0;
  for (int i = 0; i < strlen(s); i++) {
    if (current > 8) {
      printf("NO\n");
      return 0;
    }
    if (s[i] != akiba[current]) {
      if (akiba[current] == 'A') {
        current++;
        if (current > 8) {
          printf("NO\n");
          return 0;
        }
        if (s[i] != akiba[current]) {
          printf("NO\n");
          return 0;
        } else {
          current++;
        }
      } else {
        printf("NO\n");
        return 0;
      }
    } else {
      current++;
    }
  }
  if (current < 8) {
    printf("NO\n");
    return 0;
  }
  printf("YES\n");

  return 0;
}