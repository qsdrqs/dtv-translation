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

int main(void){
    long long p=0;
    int n,k,i;
    scanf("%d%d",&n,&k);
    for(i=0;i<n-1;i++){
        p++;
        p+=(p-1)/(long long)(k-1);
    }
    printf("%lld\n",p);
}
