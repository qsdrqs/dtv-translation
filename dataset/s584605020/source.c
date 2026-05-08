#include<stdio.h>
#include<stdlib.h>
#include<string.h>
#define df 0
#define MAX 200010

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef long int li;
li n;
li k;
li orbit[MAX]={};
li accum[MAX]={};
li len_orbit=0;
li term=0;
li* map[MAX];
li deg[MAX]={};
li a[MAX];


li next_orbit(li i);
li search(li t,li i);
li last_orbit(li t);

int main(){
  scanf("%d%ld",&n,&k);
  li i;
  for(i=1;i<=n;i++) map[i]=NULL;
  for(i=0;i<n;i++){
    scanf("%d",&a[i]);
    deg[a[i]]++;
    map[a[i]]=realloc(map[a[i]],sizeof(li)*deg[a[i]]);
    map[a[i]][deg[a[i]]-1]=i;
  }



  orbit[0]=0;len_orbit=1;
  i=0;
  do{
    if(df)printf("i:%d\n",i);
    i=next_orbit(i);
  }while(i!=0);
  
  if(df){
    printf("len:%d\n",len_orbit);
    for(i=0;i<len_orbit;i++){
      printf(" %d",orbit[i]);
    }
    printf("\n");
  }
  k%=term;
  if(k==0)return 0;
  i=last_orbit(k);
  if(df)printf("last:%d\n",i);
  while(i<n){
    li j=search(a[i],i);
    if(j==deg[a[i]]-1){
      printf("%d ", a[i]);
      i++;
    }else{
      i=map[a[i]][j+1]+1;
    }
  }

  return 0;
}

li next_orbit(li i){
  li j=search(a[i],i);
  if(df)printf("j:%d->",j,deg[a[i]]);
  if(j==deg[a[i]]-1){
    term++;
    j=0;
  }else j++;
  if(df)printf("j:%d,",j);
  i=map[a[i]][j]+1;
  if(i==n){term++; i=0;}
  if(df)printf("i:%d\n",i);
  accum[len_orbit]=term+1;
  orbit[len_orbit++]=i;
  return i;
}

li search(li t,li i){
  li a=0,b=deg[t]-1;
  if(map[t][b]==i)return b;
  while(b-a>0){
    li c=(a+b)/2;
    if(map[t][c]==i)return c;
    if(map[t][c]<i) a=c;
    else b=c;
  }
  return a;
}


li last_orbit(li t){
  li a=0,b=len_orbit-1;
  while(b-a>1){
    li c=(a+b)/2;
    if(accum[c]<= t)a=c;
    else b=c;
  }
  return orbit[a];
}



/// confirm df==0 ///
