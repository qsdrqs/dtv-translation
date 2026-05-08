#include <stdio.h>
#include <ctype.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int H, W;
char map[1024][1024];
char mark0[1024][1024];
char mark1[1024][1024];
int target0[1024 * 1024][2];
int target1[1024 * 1024][2];
int houkai[1024 * 1024][2];

int houkaisuru(int y, int x) {
	int count = 0;
	int i, j;
	if (map[y][x] <= 0) return 0;
	for (i = -1; i <= 1; i++) {
		for (j = -1; j <= 1; j++) {
			if (i == 0 && j == 0) continue;
			if (map[y + i][x + j] == 0) count++;
		}
	}
	return map[y][x] <= count;
}

int main(void) {
	int i, j, k;
	int count = 0;
	int (*current_target)[2] = target0, ct_num = 0;
	int (*next_target)[2] = target1, nt_num = 0;
	char (*current_mark)[1024] = mark0;
	char (*next_mark)[1024] = mark1;
	int (*target_temp)[2];
	char (*mark_temp)[1024];
	int houkai_num = 0;
	if (scanf("%d%d", &H, &W) != 2) return 1;
	for (i = 0; i < H; i++) {
		if (scanf("%1023s", map[i]) != 1) return 1;
		for (j = 0; j < W; j++) {
			if (isdigit((unsigned char)map[i][j])) {
				map[i][j] -= '0';
			} else {
				map[i][j] = 0;
			}
		}
	}
	for (i = 1; i < H - 1; i++) {
		for (j = 1; j < W - 1; j++) {
			current_target[ct_num][0] = i;
			current_target[ct_num][1] = j;
			ct_num++;
		}
	}
	for (;;) {
		nt_num = 0;
		houkai_num = 0;
		for (i = 0; i < ct_num; i++) {
			int y = current_target[i][0];
			int x = current_target[i][1];
			current_mark[y][x] = 0;
			if (houkaisuru(y, x)) {
				houkai[houkai_num][0] = y;
				houkai[houkai_num][1] = x;
				houkai_num++;
				for (j = -1; j <= 1; j++) {
					for (k = -1; k <= 1; k++) {
						if (j == 0 && k == 0) continue;
						if (next_mark[y + j][x + k] == 0) {
							next_mark[y + j][x + k] = 1;
							next_target[nt_num][0] = y + j;
							next_target[nt_num][1] = x + k;
							nt_num++;
						}
					}
				}
			}
		}
		if (houkai_num == 0) break;
		count++;
		for (i = 0; i < houkai_num; i++) {
			map[houkai[i][0]][houkai[i][1]] = 0;
		}
		ct_num = nt_num;
		target_temp = current_target;
		current_target = next_target;
		next_target = target_temp;
		mark_temp = current_mark;
		current_mark = next_mark;
		next_mark = mark_temp;
	}
	printf("%d\n", count);
	return 0;
}