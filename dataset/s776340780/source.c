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

int main(){
    int a,n,x,z = 0,an = 0;
    scanf("%d",&n);
    for(x=0;x<n;x++){
        scanf("%d",&a);
        an += a;
        z++;
    }
    printf("%d\n",an-z);

    return 0;
}


