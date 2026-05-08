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
    int S,h,m,s;
    scanf("%d\n",&S);
    h = S/3600;
    m = S%3600/60;
    s = S%60;
    printf("%d:%d:%d\n",h,m,s);
    return 0;
}
