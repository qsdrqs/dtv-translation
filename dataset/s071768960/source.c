#include<stdio.h>
#define max(x,y) ((x)>(y)?(x):(y))

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
	long n,i;
	long long a,s;
	long long ans,cmp=0;
	char op,f;
	scanf("%ld",&n);
	scanf("%lld",&a);
	f=0;
	s=0;
	ans=a;
	for(i=0;i<n-1;i++){
		scanf(" %c",&op);
		scanf("%lld",&a);
		if(f==0 && op=='-'){
			ans-=a;
			f=1;
			s=0;
		}else if(f==1 && op=='+'){
			s+=a;
		}else if(f==1 && op=='-'){
			if(s-a<=a-s){
				ans+=a-s;
				s=0;
				f=2;
			}else{
				cmp=ans+a-s;
				ans+=s-a;
				f=3;
				s=0;
			}
		}else if(f==3){
			cmp+=a;
			if(op=='+'){
				s+=a;
			}else{
				if(s-a<=a-s){
					ans+=a-s;
					s=0;
					f=4;
				}else{
					cmp=max(cmp,ans+a-s);
					ans+=s-a;
					s=0;
				}
			}
		}else{
			ans+=a;
			cmp+=a;
		}
	}
	if(s>0){
		ans+=s;
	}
	if(f>=3){
		ans=max(ans,cmp);
	}
	printf("%lld\n",ans);
	return 0;
}
