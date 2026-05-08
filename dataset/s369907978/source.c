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
	int n, m, tun, max;
	int in, out;
	int i;
	
	scanf("%d %d", &n, &m);
	tun = max = m; 
	for (i = 0; i < n; i++){
		scanf("%d %d", &in, &out);
		tun += in;
		tun -= out;
		if (tun < 0){
			printf("0\n");
			return (0);
		}
		if (max < tun){
			max = tun;
		}
	}
	
	printf("%d\n", max);
	
	return (0);
}