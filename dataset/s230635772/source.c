#include <stdlib.h>
#include <string.h>
#include <math.h>
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

long MAX(long a,long b){
    return a>b?a:b;
}
int main(int argc, const char * argv[]) {
    char s[3001],t[3001];
    scanf("%s",s);
    scanf("%s",t);
    long ls=strlen(s),lt=strlen(t);
    long dp[ls+1][lt+1];
    for(int i=0;i<=ls;i++){
        for(int j=0;j<=lt;j++){
            dp[i][j]=0;
        }
    }
    for(long i=0;i<ls;i++){
        for(long j=0;j<lt;j++){
            if(s[i]==t[j]){
                dp[i+1][j+1]=MAX(dp[i][j]+1,dp[i+1][j+1]);
            }
            dp[i+1][j+1]=MAX(dp[i+1][j],dp[i+1][j+1]);
            dp[i+1][j+1]=MAX(dp[i][j+1],dp[i+1][j+1]);
        }
    }
    int arr[3001];
    for(int i=0;i<=3000;i++){
        arr[i]=-1;
    }
    long i=ls,j=lt,v=0;
    while (i>0&&j>0){
        if(dp[i][j]==dp[i-1][j]){
            i--;
        }else if(dp[i][j]==dp[i][j-1]){
            j--;
        }else{
            arr[v]=s[i-1]-'a';
            i--;
            j--;
            v++;
        }
    }
    for(int i=v-1;i>=0;i--){
        printf("%c",arr[i]+'a');
    }
    return 0;
}
