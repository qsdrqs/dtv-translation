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

int main(void) {
int i, j, n, q, c = 0;
int S[100];
int T[100];

fscanf(stdin, "%d", &n);
for (i = 0; i < n; i++) {
fscanf(stdin, "%d", &S[i]);
}
fscanf(stdin, "%d", &q);
for (i = 0; i < q; i++) {
fscanf(stdin, "%d", &T[i]);
}

for (i = 0; i < q ; i++) {
for (j = 0; j < n; j++) {
if (T[i] == S[j]) {
c++;
break;
}
}
}

// 結果表示
printf("%d\n", c);
return 0;
}