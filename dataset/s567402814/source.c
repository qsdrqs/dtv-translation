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
  char c = getchar();
  long long int ans = 0;
  int a_num = 0;
  int ab = 0;
  while(c){
    if(c == 'A'){
      a_num++;
      if(ab){
        ab = 0;
        a_num = 1;
      }
    }else if(c == 'B'){
      if(ab){
        ab = 0;
        a_num = 0;
      }else if(a_num){
        ab = 1;
      }else{
        a_num = 0;
      }
    }else if(c == 'C'){
      if(ab){
        ans += a_num;
        ab = 0;
      }else{
        a_num = 0;
      }
    }else{
      break;
    }
    c = getchar();
  }
  printf("%lld\n", ans);
  return 0;
}
