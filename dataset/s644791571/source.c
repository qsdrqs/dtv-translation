
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

int main()
{   int n,m;
    scanf("%d%d",&n,&m);
    int set[n+1];
    for(int i=0;i<=n;i++)set[i]=0;
    for(int i=0;i<m;i++){
        int tmp;
        scanf("%d",&tmp);
        set[tmp]++;
        scanf("%d",&tmp);
        set[tmp]++;
    }
    for(int i=1;i<=n;i++)if(set[i]%2==1){
        printf("NO");
        return 0;
    }
    printf("YES");
    return 0;
}
