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

int main(){
char str[5];
  for(int i= 0; i<5;i++){
    scanf("%s", &str[i]);
  }
  
  for(int j = 0; j<5; j++){
    if(str[j] == 'A' && str[j+1] == 'C'){
      printf("Yes\n");
      return 0;
    }
  }    
        printf("No\n");
         return 0;
      
  }