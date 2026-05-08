#include <stdio.h>
#include <ctype.h>
#include <stdlib.h>
#define MAX_NUM_CHILDREN 5000

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int comp_ints(const void* a, const void* b) { return *(int*)a - *(int*)b; }

int solve()
{
    char ch;

    if((ch = getchar()) == '[')
    {
        int res;

        if(isdigit((int)(ch = getchar())))
        {
            int t;
            ungetc(ch, stdin);
            scanf("%d", &t);
            res = (t + 1) / 2;
        }
        else
        {
            int cost[MAX_NUM_CHILDREN], count = 0, t;
            ungetc(ch, stdin);
            while((t = solve()) != -1)
                cost[count++] = t;
            qsort(cost, count, sizeof(int), comp_ints);
            for(res = t = 0, count = (1 + count) / 2; t < count; t++)
                res += cost[t];
        }

        getchar();              /* pop ']' */
        return res;
    }

    ungetc(ch, stdin);
    return -1;
}

int main(void)
{
    int t;

    scanf("%*d%*c");

    while((t = solve()) != -1)
        printf("%d\n", t), getchar();

    return 0;
}