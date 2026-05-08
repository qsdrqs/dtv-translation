#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int main()
{
	int N;

	scanf("%d", &N);

	int H[N];
	int flag = 0;

	for(int i = 0;i < N;i++) {
		scanf("%d", &H[i]);
	}

	for(int i = N - 1;i > 0;i--) {
		if(H[i] >= H[i - 1]) {
		} else if(H[i - 1] - H[i] == 1) {
			H[i - 1] -= 1;
		} else {
			flag = 1;
			break;
		}
	}
	
	if(flag == 0) {
		printf("Yes\n");
	} else {
		printf("No\n");		
	}

}