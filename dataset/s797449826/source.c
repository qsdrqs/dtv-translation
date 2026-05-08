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

int main(void)
{
    int n;
    scanf("%d", &n);

    int *A = malloc(sizeof(int) * n);
    int i;
    for (i = 0; i < n; i++) scanf("%d", A + i);

    int m;
    scanf("%d", &m);

    int *B = malloc(sizeof(int) * m);
    for (i = 0; i < m; i++) scanf("%d", B + i);

    int ans;
    if (n < m) {
        ans = 1;
    }
    else {
        ans = 0;
        n = m;
    }
    for (i = 0; i < n; i++) {
        if (A[i] < B[i]) {
            ans = 1;
            break;
        }
        else if (A[i] > B[i]) {
            ans = 0;
            break;
        }
    }

    printf("%d\n", ans);

    free(A);
    free(B);

    return 0;
}
