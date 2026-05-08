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

long long int r, s ,p;

long long int func(char c){
    if(c == 'r'){
        return p;
    }
    if(c == 's'){
        return r;
    }
    if(c == 'p'){
        return s;
    }
    return 0;
}

int main(){
    int n, k;
    scanf("%d %d", &n, &k);
    scanf("%lld %lld %lld", &r, &s, &p);
    char s[n+1];
    scanf("%s", s);
    long long int ans = 0;
    for(int i=0; i<k; i++){
        char pre = s[i];
        long long int buf = func(s[i]);
        for(int j=i+k; j<n; j+=k){
            if(pre == s[j]){
                pre = '&';
            }else{
                buf += func(s[j]);
                pre = s[j];
            }
        }
        ans += buf;
        //printf("%lld\n", ans);
    }
    printf("%lld", ans);

    return 0;
}