#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// 内部定数
#define D_HUMAN_MAX		100000									// 最大人数
#define D_VTX_MAX		200000									// 最大頂点数

// 内部変数
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

static FILE *szpFpI;											// 入力
static int siHCnt;												// 人数
static int siLCnt;												// 言語数
static int si1VNo[D_VTX_MAX];									// 代表頂点[頂点]

// 内部変数 - テスト用
#ifdef D_TEST
	static int siRes;
	static FILE *szpFpA;
#endif

// 代表頂点 - 取得
int
fGetVNo(
	int piVNo					// <I> 頂点 0～
)
{
	// 自分が代表かチェック
	if (si1VNo[piVNo] == piVNo) {
		return piVNo;
	}

	// 下位へ
	si1VNo[piVNo] = fGetVNo(si1VNo[piVNo]);

	return si1VNo[piVNo];
}

// 実行メイン
int
fMain(
	int piTNo					// <I> テスト番号 1～
)
{
	int i, j, liRet;
	char lc1Buf[1024], lc1Out[1024];

	// 入力 - セット
#ifdef D_TEST
	sprintf(lc1Buf, ".\\Test\\T%d.txt", piTNo);
	szpFpI = fopen(lc1Buf, "r");
	sprintf(lc1Buf, ".\\Test\\A%d.txt", piTNo);
	szpFpA = fopen(lc1Buf, "r");
	siRes = 0;
#else
	szpFpI = stdin;
#endif

	// 人数・言語数 - 取得
	fgets(lc1Buf, sizeof(lc1Buf), szpFpI);
	sscanf(lc1Buf, "%d%d", &siHCnt, &siLCnt);

	// 代表頂点 - 初期化
	for (i = 0; i < siHCnt + siLCnt; i++) {
		si1VNo[i] = i;
	}

	// 言語 - 取得
	int liVNo1, liVNo2;
	for (i = 0; i < siHCnt; i++) {

		// 言語数 - 取得
		int liCnt;
		fscanf(szpFpI, "%d", &liCnt);

		// 言語 - 取得
		for (j = 0; j < liCnt; j++) {
			int liLNo;
			fscanf(szpFpI, "%d", &liLNo);
			liLNo += siHCnt - 1;

			// 代表頂点 - 取得
			liVNo1 = fGetVNo(i);
			liVNo2 = fGetVNo(liLNo);

			// 代表頂点 - 統一
			if (liVNo1 != liVNo2) {
				si1VNo[liVNo2] = liVNo1;
			}
		}
		fgets(lc1Buf, sizeof(lc1Buf), szpFpI);
	}

	// 代表頂点 - 一致チェック
	liRet = 0;
	liVNo1 = fGetVNo(0);
	for (i = 1; i < siHCnt; i++) {
		liVNo2 = fGetVNo(i);
		if (liVNo1 != liVNo2) {			// 不一致
			liRet = -1;
			break;
		}
	}

	// 結果 - セット
	if (liRet == 0) {
		sprintf(lc1Out, "YES\n");
	}
	else {
		sprintf(lc1Out, "NO\n");
	}

	// 結果 - 表示
#ifdef D_TEST
	fgets(lc1Buf, sizeof(lc1Buf), szpFpA);
	if (strcmp(lc1Buf, lc1Out)) {
		siRes = -1;
	}
#else
	printf("%s", lc1Out);
#endif

	// 残データ有無
#ifdef D_TEST
	lc1Buf[0] = '\0';
	fgets(lc1Buf, sizeof(lc1Buf), szpFpA);
	if (strcmp(lc1Buf, "")) {
		siRes = -1;
	}
#endif

	// テストファイルクローズ
#ifdef D_TEST
	fclose(szpFpI);
	fclose(szpFpA);
#endif

	// テスト結果
#ifdef D_TEST
	if (siRes == 0) {
		printf("OK %d\n", piTNo);
	}
	else {
		printf("NG %d\n", piTNo);
	}
#endif

	return 0;
}

int
main()
{

#ifdef D_TEST
	int i;
	for (i = D_TEST_SNO; i <= D_TEST_ENO; i++) {
		fMain(i);
	}
#else
	fMain(0);
#endif

	return 0;
}

