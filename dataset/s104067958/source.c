#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define MOD (1000000000+7)

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef long long ll;

int compare_char(const void* left, const void* right) {
    char *left_char = (char *)left;
    char *right_char = (char *)right;
    
    return strcmp(left_char,right_char);
}

int gcd(int a,int b){
  if(b == 0) return a;
  else return gcd(b, a%b);
}

ll modpow(ll a,ll n){
  ll res = 1;
  while(n>0){
    if(n % 2 == 1) res = res*a%MOD;
    a = a*a%MOD;
    n /= 2;
  }
  return res;
}

ll modinv(ll a){
  return modpow(a, MOD-2);
}

ll com(ll n, ll r){
  ll res = 1;
  for(int k=1;k<=r;k++){
    res = res * (n-(k-1)) % MOD;
    res = res * modinv(k) % MOD;
  }
  return res;
}

int main(void){
  int n, a, b, i, result=0;
  long int tmp=1;
  
  scanf("%d %d %d", &n, &a, &b);
  
  result = modpow(2,n);
  result--;
  if(result<0) result+=MOD;
  ll rm = com(n,a)+com(n,b);
  rm%=MOD;
  result-=rm;
  if(result<0)result+=MOD;
  
  printf("%d", (int) result%MOD);
}