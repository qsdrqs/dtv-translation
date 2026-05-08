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

int main(void)
{
    int a, b, n;
    while (scanf("%d%d%d",&a,&b,&n) != EOF) {
        int res=0;
        do {
            a = 10*(a%b);
            res += a/b;
        } while (--n);
        printf("%d\n", res);
    }
    return 0;
}