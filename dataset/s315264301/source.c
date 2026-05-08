#include <stdio.h>
#include <stdlib.h>
#define maxSize (int)(1e5 + 1)

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
	int i;
	char *s, first, last;
	s = (char *)malloc(sizeof(char) * maxSize);
	scanf("%s", s);
	first = s[0];
	for(i = 1; ; i++){
		if(s[i] == '\0'){
			last = s[i - 1];
			break;
		}
	}
	if((first == last && i % 2 == 1) || (first != last && i % 2 == 0)){
		printf("Second\n");
	}
	else{
		printf("First\n");
	}
	return 0;
}