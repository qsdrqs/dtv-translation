#include <unistd.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

char ibuf[(11<<18)+5];
char *ibufe = ibuf-1;

extern inline void readall(){
  int k, t = 0;
  while((k=read(STDIN_FILENO, ibuf+t, sizeof(ibuf)-t))>0) t += k;
}

int read_uint(){
  int x=0;
  while(*(++ibufe) <'0');
  do {
    x *= 10;
    x += *ibufe-'0';
  } while(*(++ibufe) >='0');

  return x;
}

char buf[40];
char *bufe = buf;

void write_uintln(int x){
  int i;
  static char tmp[13];
  if(x==0){
    *bufe++ = '0';
    *bufe++ = '\n';
    return;
  }

  for(i=0; x; i++){
    tmp[i] = '0' + x % 10;
    x /= 10;
  }
  for(i--; i >= 0; i--){
    *bufe++ = tmp[i];
  }
  *bufe++ = '\n';
}

extern inline void writeall(){
  int k, t = 0;
  while((k=write(STDOUT_FILENO, buf+t, bufe-buf-t))>0) t += k;
}


#define MAX(x, y) ((x) > (y) ? (x) : (y))

int n;
int A[1<<18];
int B[1<<18];

void zeta(int n){
  int i, j;
  int m = 1 << n;
  for(i=1;i<m;i<<=1){
    for(j=0;j<m;j++){
      if(j&i){
        int max = MAX(A[j], A[j^i]);
        B[j] = MAX(max^A[j]^A[j^i], MAX(B[j], B[j^i]));
        A[j] = max;
      }
    }
  }
}


int main(){
  int i, max;
  readall();
  n = read_uint();
  for(i=0;i<(1<<n);i++){
    A[i] = read_uint();
  }
  zeta(n);
  max = 0;
  for(i=1;i<(1<<n);i++){
    max = MAX(max, A[i]+B[i]);
    write_uintln(max);
  }
  writeall();
  return 0;
}
