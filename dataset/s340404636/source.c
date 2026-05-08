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

int main(void)
{
    int n, i;
    scanf("%d", &n);
    for(i = 0; i < n; i++){
        char done[1024][73];
        char org[73];
        int num = 0, len, j;

        scanf("%s", org);
        len = strlen(org);

        for(j = 1; j < len; j++){
            int k;
            char first[2][72], second[2][72];
            for(k = 0; k < j; k++){
                first[0][k] = first[1][j - 1 - k] = org[k];
            }
            first[0][k] = first[1][k] = '\0';
            for(k = j; k < len; k++){
                second[0][k - j] = second[1][len -1 - k] = org[k];
            }
            second[0][len - j] = second[1][len - j] = '\0';
            //printf("first: %s, rev: %s\n", first[0], first[1]);
            //printf("second: %s, rev: %s\n", second[0], second[1]);

            int l;
            for(k = 0; k < 2; k++){
                for(l = 0; l < 2; l++){
                    int m;
                    char temp[73];
                    strcpy(temp, first[k]);
                    strcat(temp, second[l]);
                    for(m = 0; m < num; m++)
                        if(strcmp(temp, done[m]) == 0)
                            break;
                    if(m == num){
                        strcpy(done[num], temp);
                        num++;
                    }
                    strcpy(temp, second[l]);
                    strcat(temp, first[k]);
                    for(m = 0; m < num; m++)
                        if(strcmp(temp, done[m]) == 0)
                            break;
                    if(m == num){
                        strcpy(done[num], temp);
                        num++;
                    }
                }
            }
        }
        //for(j = 0; j < num; j++)
        //    printf("%s\n", done[j]);

        printf("%d\n", num);
    }
    return 0;
}