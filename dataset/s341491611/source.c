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
    int n,s,i,line[20000],ans,sum,o;
    for(;ans=0,scanf("%d %d",&n,&s),n+s;){
        for(i=0;i<n;i++)
            scanf("%d",&line[i]);
        for(i=0;i<n-1;i++)
            for(o=i+1;sum=0,o<n;o++){
                sum+=line[i]+line[o];
                if(sum > s)
                    ans++;
            }
        printf("%d\n",ans);
    }
    return 0;
}