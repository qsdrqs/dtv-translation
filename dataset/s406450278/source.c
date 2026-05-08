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

int n,k,s;
int ans;
 
void dfs(int num,int cnt,int sum){
  if(sum==s && cnt == k)
    ans++;
  if(num > n)
    return;
  if(cnt == k)
    return;
  dfs(num+1,cnt,sum);
  dfs(num+1,cnt+1,sum+num);
}
 
int main(){
   
  while(scanf("%d%d%d",&n,&k,&s),n+k+s!=0){
    ans=0;
    dfs(1,0,0);
    printf("%d\n",ans);
  }
   
  return 0;
}