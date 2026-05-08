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

int main() {
	int n;
	int data[265][2] = {0};  //data[i][0]...x data[i][1]...y
	int x_max, x_min, y_max, y_min;
	int ni, di;
	int i;

	do {
		data[0][0] = data[0][1] = 0;
		x_max = x_min = y_max = y_min = 0;

		scanf("%d", &n);
		if(!n)
			break;

		for(i = 1; i < n; i++) {
			scanf("%d %d", &ni, &di);

			switch(di) {
				case 0:
					data[i][0] = data[ni][0] - 1;
					data[i][1] = data[ni][1];
					break;
				case 1:
					data[i][1] = data[ni][1] - 1;
					data[i][0] = data[ni][0];
					break;
				case 2:
					data[i][0] = data[ni][0] + 1;
					data[i][1] = data[ni][1];
					break;
				case 3:
					data[i][1] = data[ni][1] + 1;
					data[i][0] = data[ni][0];
					break;
			}

			if(data[i][0] > x_max)
				x_max = data[i][0];
			if(data[i][0] < x_min)
				x_min = data[i][0];
			if(data[i][1] > y_max)
				y_max = data[i][1];
			if(data[i][1] < y_min)
				y_min = data[i][1];
		}

		printf("%d %d\n", x_max - x_min + 1, y_max - y_min + 1);
	} while(1);

	return 0;
}