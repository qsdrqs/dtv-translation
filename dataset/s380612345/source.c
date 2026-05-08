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

long long dp[51][51][2501];

int main(void){
  int N,A;
  scanf("%d%d",&N,&A);

  int x[N];
  for(int i = 0;i < N;i++){
    scanf("%d",&x[i]);
  }

  dp[0][0][0] = 1;
  for(int i = 1;i <= N;i++){
    for(int j = 0;j <= N;j++){
      for(int k = 0;k <= 2500;k++){
        if(k >= x[i-1] && j != 0){
          dp[i][j][k] = dp[i-1][j][k]+dp[i-1][j-1][k-x[i-1]];
        }else{
          dp[i][j][k] = dp[i-1][j][k];
        }
      }
    }
  }

  long long ans = 0;
  for(int i = 1;i <= N;i++){
    ans += dp[N][i][A*i];
  }

  printf("%lld\n",ans);

  return 0;
}