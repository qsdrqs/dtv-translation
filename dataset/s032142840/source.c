#include <stdio.h>
#include <stdlib.h>
#include <limits.h>

#define MAX_N  ((1 << 18) - 1)
#define MAX_L  100000

#define min(a, b)  ((a) < (b) ? (a) : (b))
#define max(a, b)  ((a) > (b) ? (a) : (b))

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int n;
int val[MAX_N], wgt[MAX_N];

int dpn;

typedef struct wgtval {
  int wgt, val;
} wgtval;

struct wgtval_list {
  int size;
  wgtval *list;
} dp[MAX_N];

#define set_wgtval(wv, w, v)  ((wv).wgt = (w), (wv).val = (v))

int compare_wgt(const void *a, const void *b)
{
  const wgtval *p = a;
  const wgtval *q = b;
  if (p->wgt == q->wgt) {
    return p->val < q->val ? -1 :
           p->val > q->val ?  1 : 0;
  }
  return p->wgt < q->wgt ? -1 : 1;
}

void compute_dp()
{
  int u;

  /* initialize */
  dpn = min(n, 1 << 12);
  dp[0].size = 2;
  dp[0].list = malloc(2 * sizeof(wgtval));
  set_wgtval(dp[0].list[0], 0, 0);
  set_wgtval(dp[0].list[1], wgt[0], val[0]);

  /* compute the dp table */
  for (u = 1; u < dpn; u++) {
    int parent = (u - 1) / 2;
    int tail, i;

    dp[u].size = dp[parent].size * 2;
    dp[u].list = malloc(dp[u].size * sizeof(wgtval));
    for (i = 0; i < dp[parent].size; i++) {
      dp[u].list[i * 2] = dp[parent].list[i];
      set_wgtval(dp[u].list[i * 2 + 1],
                 dp[parent].list[i].wgt + wgt[u],
                 dp[parent].list[i].val + val[u]);
    }
    qsort(dp[u].list, dp[u].size, sizeof(wgtval), compare_wgt);

    /* remove unnecessary entries */
    tail = 0;
    for (i = 1; i < dp[u].size; i++) {
      if (dp[u].list[i].wgt > MAX_L) {
        break;
      }
      if (dp[u].list[tail].wgt == dp[u].list[i].wgt) {
        dp[u].list[tail] = dp[u].list[i];
      } else if (dp[u].list[tail].val < dp[u].list[i].val) {
        tail++;
        dp[u].list[tail] = dp[u].list[i];
      }
    }
    dp[u].size = tail + 1;
  }
}

int bsearch_right(wgtval *list, int size, int target)
{
  int lo = 0;
  int hi = size;
  while (lo < hi) {
    int mid = (lo + hi) / 2;
    if (target < list[mid].wgt) {
      hi = mid;
    } else {
      lo = mid + 1;
    }
  }
  return lo;
}

int solve(int u, int l)
{
  int parent;
  int s;

  if (u < dpn) {
    int x = bsearch_right(dp[u].list, dp[u].size, l) - 1;
    return dp[u].list[x].val;
  }

  parent = (u - 1) / 2;
  s = solve(parent, l);
  if (l >= wgt[u]) {
    int t = val[u] + solve(parent, l - wgt[u]);
    s = max(s, t);
  }
  return s;
}

int main()
{
  int i, q;

  scanf("%d", &n);
  for (i = 0; i < n; i++) {
    scanf("%d%d", &val[i], &wgt[i]);
  }

  compute_dp();

  scanf("%d", &q);
  for (i = 0; i < q; i++) {
    int u, l;
    scanf("%d%d", &u, &l);
    printf("%d\n", solve(u - 1, l));
  }

  return 0;
}
