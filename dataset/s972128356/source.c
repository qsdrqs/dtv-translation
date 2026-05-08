#include<stdio.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int min(int a, int b){
  return (a < b) ? a : b;
}

int main(){
  int n, m, k, i, j, a, b, cost, time, p, q, r, Time[100][100], Cost\
[100][100];

  while(scanf("%d%d", &n, &m), n+m){
    for(i=0; i<100; i++){
      for(j=0; j<100; j++){
        if(i!=j){
          Time[i][j] = 100000;
          Cost[i][j] = 100000;
        }else{
          Time[i][j] = 0;
          Cost[i][j] = 0;
        }
      }
    }
    for(i=0; i<n; i++){
      scanf("%d%d%d%d", &a, &b, &cost, &time);
      Cost[a-1][b-1] = cost;
      Cost[b-1][a-1] = cost;
      Time[a-1][b-1] = time;
      Time[b-1][a-1] = time;
    }
    for(k=0; k<m; k++){
      for(i=0; i<m; i++){
        for(j=0; j<m; j++){
          Cost[i][j] = min(Cost[i][j], Cost[i][k]+Cost[k][j]);
          Time[i][j] = min(Time[i][j], Time[i][k]+Time[k][j]);
        }
      }
    }
    scanf("%d", &k);
    for(i=0; i<k; i++){
      scanf("%d%d%d", &p, &q, &r);
      if(r==0){
        printf("%d\n", Cost[p-1][q-1]);
      }else{
        printf("%d\n", Time[p-1][q-1]);
      }
    }
  }
  return 0;
}