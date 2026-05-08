#include <stdio.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>

#define GYOU_MAX 256
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

void sort_string(char Text[], int size, int sign) {
	char a;

	for (int i = 0; i < size - 1; i++) {
		for (int j = 0; j < size - 1 - i; j++) {
			if (sign > 0) {
				if (Text[j] > Text[j + 1]) {

					a = Text[j];
					Text[j] = Text[j + 1];
					Text[j + 1] = a;
				}
			}
			else {
				if (Text[j] < Text[j + 1]) {

					a = Text[j];
					Text[j] = Text[j + 1];
					Text[j + 1] = a;

				}
			}
		}

	}

}

int main(void){

	char s[101], t[101];
	scanf("%s%s", s, t);
	sort_string(s, strlen(s),1);
	sort_string(t, strlen(t), 0);
	if (strcmp(s, t) < 0) {
		printf("Yes\n");
	}
	else {
		printf("No\n");
	}

	return 0;
}