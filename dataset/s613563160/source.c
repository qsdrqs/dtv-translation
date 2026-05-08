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

char* to_code(char c) {
	switch(c) {
		case ' ': return "101";
		case '\'': return "000000";
		case ',': return "000011";
		case '-': return "10010001";
		case '.': return "010001";
		case '?': return "000001";
		case 'A': return "100101";
		case 'B': return "10011010";
		case 'C': return "0101";
		case 'D': return "0001";
		case 'E': return "110";
		case 'F': return "01001";
		case 'G': return "10011011";
		case 'H': return "010000";
		case 'I': return "0111";
		case 'J': return "10011000";
		case 'K': return "0110";
		case 'L': return "00100";
		case 'M': return "10011001";
		case 'N': return "10011110";
		case 'O': return "00101";
		case 'P': return "111";
		case 'Q': return "10011111";
		case 'R': return "1000";
		case 'S': return "00110";
		case 'T': return "00111";
		case 'U': return "10011100";
		case 'V': return "10011101";
		case 'W': return "000010";
		case 'X': return "10010010";
		case 'Y': return "10010011";
		case 'Z': return "10010000";
	}
	return "";
}

char to_char(char* s) {
	int i, n;
	for(i = 0, n = 0; i < 5; i++) {
		n <<= 1;
		n += s[i] - '0';
	}

	if(n < 26)
		return 'A' + n;

	switch(n) {
		case 26: return ' ';
		case 27: return '.';
		case 28: return ',';
		case 29: return '-';
		case 30: return '\'';
		case 31: return '?';
	}
	return '\0';
}

int main() {
	int c;
	char in[32];
	int head = 0, tail = 0;
	int i;

	while(1) {
		head = tail = 0;
		while((c = getchar()) != '\n') {
			char* code;
			int len;

			if(c == EOF)
				return 0;

			code = to_code(c);
			len = strlen(code);

			for(i = 0; i < len; i++) {
				in[tail] = code[i];
				tail = (tail + 1) % 32;
			}

			while(((tail < head ? 32 : 0) + tail - head) / 5) {
				char tmp[8];
				for(i = 0; i < 5; i++) {
					tmp[i] = in[head];
					head = (head + 1) % 32;
				}
				tmp[5] = '\0';

				putchar(to_char(tmp));
			}
		}

		while(((tail < head ? 32 : 0) + tail - head) % 5) {
			in[tail] = '0';
			tail = (tail + 1) % 32;
		}

		while(((tail < head ? 32 : 0) + tail - head) / 5) {
			char tmp[8];
			for(i = 0; i < 5; i++) {
				tmp[i] = in[head];
				head = (head + 1) % 32;
			}
			tmp[5] = '\0';

			putchar(to_char(tmp));
		}
		putchar('\n');
	}
	return 0;
}