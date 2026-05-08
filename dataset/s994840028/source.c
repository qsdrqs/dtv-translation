#include <stdio.h>
#include <string.h>

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
	int p_tarou;
	int p_hanako;
	char c_tarou[100];
	char c_hanako[100];
	int n;
	int i;
	
	scanf("%d", &n);
	
	p_tarou = 0;
	p_hanako = 0;
	for (i = 0; i < n; i++){
		scanf("%s %s", c_tarou, c_hanako);
		if (strcmp(c_tarou, c_hanako) == 0){
			p_tarou++;
			p_hanako++;
		}
		else if (strcmp(c_tarou, c_hanako) < 0){
			p_hanako += 3;
		}
		else {
			p_tarou += 3;
		}
	}
	printf("%d %d\n", p_tarou, p_hanako);
	
	return (0);
}