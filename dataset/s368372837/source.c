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
        
	long n_customer;
	scanf("%ld",&n_customer);
	
	long long sold;
	scanf("%lld",&sold);
	sold -= 1;
	
	if(n_customer == 1){
		printf("%lld",sold);
		return 0;
	}
	
	long i = 1;
	long price = 2;
	
	while(1){
		long money;
		scanf("%ld",&money);
		if(money < price)
			i++;
		else if(money == price){
			price++;
			i++;
		}else{
			if(money % price == 0){
				sold += money / price -1;
			}else{
				sold += money / price;
			}
			i++;
		}
		if(i == n_customer)
			break;
	}
	printf("%lld",sold);

	return 0;
}