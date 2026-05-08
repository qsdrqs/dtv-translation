#include<stdio.h>
#include<stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int comp(const void *p1,const void *p2){
  int n1=*(const int *)p1;
  int n2=*(const int *)p2;
  return n2-n1;
}

int main(void){
  int N,K,contest=0;
  char str[16];
  int num[26]={0};
  int i,j,k;

  scanf("%d%d%*c",&N,&K);
  for(i=0;i<N;i++){
    scanf("%s%*c",str);
    num[str[0]-'A']++;
  }

  do{
    qsort(num,26,sizeof(int),comp);
    for(i=0;i<K;i++){
      if(num[i]==0){
	printf("%d\n",contest);
	return 0;
      }
      num[i]--;
    }
    contest++;
  }while(1);
      

  return 0;
}
