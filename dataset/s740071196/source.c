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

int main(void)
{
	int n, c, f;
	int i;
	
	while (scanf("%d", &n), n){
		c = 0;
		for (i = 5; i <= n; i += 5){
			f = i;
			while (f % 5 == 0){
				c++;
				f /= 5;
			}
		}
		printf("%d\n", c);
	}
	return (0);
}