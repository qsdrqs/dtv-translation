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
	int n, a;
	
	while (scanf("%d", &n) != EOF){
		a = (n * (n - 1)) / 2 + (n + 1);
		printf("%d\n", a);
	}
	
	return (0);
}