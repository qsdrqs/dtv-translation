#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main (void)
{
    intmax_t N;
    char S[30001];
    uint16_t digit[30000] = {};
    intmax_t ans = 0;

    scanf("%jd", &N);
    scanf("%s", S);

    for (int i = 0; i < 10; i++) {
        int pos1 = 0, pos2 = 0, pos3 = 0;
        while ((pos1 < N) && ((S[pos1] - '0') != i)) pos1++;
        for (int j = 0; j < 10; j++) {
            pos2 = pos1 + 1;
            while ((pos2 < N) && ((S[pos2] - '0') != j)) pos2++;
            for (int k = 0; k < 10; k++) {
                pos3 = pos2 + 1;
                while ((pos3 < N) && ((S[pos3] - '0') != k)) pos3++;
                if (pos3 < N) ans++;
            }
        }
    }

    printf("%jd\n", ans);

    return 0;
}
