// AOJ 1021 Emacs-like Editor
// 2018.3.2 bal4u

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

char text[101][1005]; int len[101];
char buf[1005]; int blen;

int main()
{
	int N, r, c, rr;
	char cmd[5], *p, *q, *t;

	N = -1;
	do {
		fgets(p=text[++N], 1005, stdin);
		while (*p >= ' ') p++; *p = 0;
		len[N] = p - text[N];
	} while (strcmp(text[N], "END_OF_TEXT"));
	r = 0, c = 0, blen = 0;
	while (1) {
		fgets(cmd, 5, stdin); if (*cmd == '-') break;
		if      (*cmd == 'a') c = 0;
		else if (*cmd == 'e') c = len[r];
		else if (*cmd == 'p') { c = 0, r--; if (r < 0) r = 0; }
		else if (*cmd == 'n') { c = 0, r++; if (r >= N) r = N - 1; if (r < 0) r = 0; }
		else if (*cmd == 'f') { if (c < len[r]) c++; else if (r < N-1) r++, c = 0; }
		else if (*cmd == 'b') {	if (c > 0) c--;	else if (r > 0) r--, c = len[r]; }
		else if (*cmd == 'd') {
			if (c == len[r]) {
				if (r < N-1) {
					memcpy(text[r]+len[r], text[r+1], len[r+1]+1);
					len[r] += len[r+1];
					for (rr = r+2; rr < N; rr++) {
						memcpy(text[rr-1], text[rr], len[rr]+1);
						len[rr-1] = len[rr];
					}
					N--;
				}
			} else {
				p = text[r] + c;
				while (*p) *p = *(p+1), p++;
				len[r]--;
			}
		}
		else if (*cmd == 'k') {
			if (c == len[r]) {
				if (r < N-1) {
					blen = -1;
					memcpy(text[r]+len[r], text[r+1], len[r+1]+1);
					len[r] += len[r+1];
					for (rr = r+2; rr < N; rr++) {
						memcpy(text[rr-1], text[rr], len[rr]+1);
						len[rr-1] = len[rr];
					}
					N--;
				}
			} else {
				blen = len[r]-c, memcpy(buf, text[r]+c, blen+1);
				len[r] -= blen; if (len[r] < 0) len[r] = 0; text[r][len[r]] = 0;
				c = len[r];
			}
		}
		else if (*cmd == 'y') {
			if (blen == -1) {
				for (rr = N-1; rr > r; rr--) {
					memcpy(text[rr+1], text[rr], len[rr]+1);
					len[rr+1] = len[rr];
				}
				N++;
				len[r+1] = len[r]-c, memcpy(text[r+1], text[r]+c, len[r+1]+1);
				len[r] = c, text[r][len[r]] = 0;
				r++, c = 0;
			} else if (blen > 0) {
				t = text[r]+c, p = text[r]+len[r], q = p+blen;
				while (p >= t) *q-- = *p--;
				memcpy(t, buf, blen);
				c += blen, len[r] += blen;
			}
		}
	}
	for (r = 0; r < N; r++) puts(text[r]);
	return 0;
}
