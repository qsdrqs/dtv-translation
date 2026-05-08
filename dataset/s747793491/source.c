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

int bar[30][9];

int check(int n, int m, int h, int d);

int main(void) {
	int n, m, h, d;
	char str[10];
	int i, j, k;
	int flag;
	
	while (1) {
		scanf("%d", &n);
		if (!n)
			break;
		scanf("%d", &m);
		scanf("%d", &h);
		scanf("%d", &d);
		for (i = 0; i < d; i++) {
			scanf("%s", str);
			for (j = 0; j < n-1; j++) {
				bar[i][j] = str[j] - '0';
			}
		}
		if (check(n, m, h, d))
			printf("0\n");
		else {
			for (i = 0; i < d; i++) {
				for (j = 0; j < n-1;j++) {
					if (j == 0 && !bar[i][j] && !bar[i][j+1])
						flag = 1;
					else if (j == n-2 && n-1 != 1 && !bar[i][j] && !bar[i][j-1])
						flag = 1;
					else if (j > 0 && j < n-2 && !bar[i][j-1] && !bar[i][j] && !bar[i][j+1])
						flag = 1;
					else
						flag = 0;
					if (flag) {
						bar[i][j] = 1;
						if (check(n, m, h, d)) {
							printf("%d %d\n", i+1, j+1);
							i = d;j = n;
						}
						else
							bar[i][j] = 0;
					}
				}
			}
			if (i == d && j == n-1)
				printf("1\n");
		}
	}
	return 0;
}

int check(int n, int m, int h, int d) {
	int i;
	for (i = 0; i < d; i++) {
		if (m == 1 && bar[i][m-1])
			m++;
		else if (m == n && bar[i][m-2])
			m--;
		else if (m != 1 && m != n) {
			if (bar[i][m-2])
				m--;
			else if (bar[i][m-1])
				m++;
		}
	}
	
	if (m == h)
		return 1;
	else
		return 0;
}