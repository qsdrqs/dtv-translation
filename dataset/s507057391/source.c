#include <stdio.h>
#include <stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct{
	int no;
	int cnt;
}DATA;
 
int cmp( const void *p, const void *q ) {
    return ((DATA*)q)->cnt - ((DATA*)p)->cnt;
}
 
int main(void){
	
	int i, n, tmp, cnt, ans;
	
	scanf("%d", &n);
	
	int v_odd[n / 2], v_even[n / 2];
	DATA cnt_odd[100000], cnt_even[100000];
	for(i = 0; i < 100000; i++){
		cnt_odd[i].no = i + 1;
		cnt_odd[i].cnt = 0;
		cnt_even[i].no = i + 1;
		cnt_even[i].cnt = 0;
	}
	
	for(i = 0; i < n; i++){
		if(i % 2 == 0){
			scanf("%d", &v_even[i / 2]);
			cnt_even[v_even[i / 2] - 1].cnt++;
		}else{
			scanf("%d", &v_odd[i / 2]);
			cnt_odd[v_odd[i / 2] - 1].cnt++;
		}
	}
	
	
	
	qsort(cnt_even, 100000, sizeof(DATA), cmp);
	qsort(cnt_odd, 100000, sizeof(DATA), cmp);
	
	
	
	
	// printf("odd1 : %d (%d)\nodd2 : %d (%d)\neven1 : %d (%d)\neven2 : %d (%d)\n", cnt_odd[0].no, cnt_odd[0].cnt, cnt_odd[1].no, cnt_odd[1].cnt, cnt_even[0].no, cnt_even[0].cnt, cnt_even[1].no, cnt_even[1].cnt);
	
	if(cnt_odd[0].no == cnt_even[0].no){
		int a[2];
		a[0] = (n / 2 - cnt_odd[1].cnt) + (n / 2 - cnt_even[0].cnt);
		a[1] = (n / 2 - cnt_odd[0].cnt) + (n / 2 - cnt_even[1].cnt);
		if(a[0] < a[1]){
			ans = a[0];
		}else{
			ans = a[1];
		}
	}else{
		ans = (n / 2 - cnt_odd[0].cnt) + (n / 2 - cnt_even[0].cnt);
	}
	
	printf("%d", ans);
	
	
	return 0;
}