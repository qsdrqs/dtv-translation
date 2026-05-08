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

int main() {
	char o[51], e[51];
	scanf("%s%s", o, e);
	for (int i = 0; i < strlen(o) * 2; i++) {
		if (i % 2 == 0) {
			printf("%c", o[i / 2]);
		} else {
			if (i == strlen(o) * 2 - 1 && strlen(o) - strlen(e) == 1) break;
			printf("%c", e[(i - 1) / 2]);
		}
	}
	printf("\n");
	return 0;
}