#include <stdio.h>
#include <stdlib.h>

#define MAX_N   100000

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

long long result[10];

struct Node {
    int val, x, y;
    long long key;
    struct Node *lch, *rch;
};
typedef struct Node node;

node *modify (node *p, int new_x, int new_y, long long new_key){
    if(p == NULL){
        node *q = (node*)malloc(sizeof(node));
        q->val = 1;
        q->x = new_x; q->y = new_y;
        q->key = new_key;
        q->lch = q->rch = NULL;
        return q;
    }
    else if (p->key == new_key){
        p->val++;
        return p;
    }
    else {
        if (new_key < p->key) p->lch = modify(p->lch, new_x, new_y, new_key);
        else p->rch = modify(p->rch, new_x, new_y, new_key);
        return p;
    }
}

void answer(node *p){
    if (p != NULL){
        answer(p->lch);
        result[p->val]++;
        result[0]--;
        answer(p->rch);
    }
}

void release(node *p){
    if (p != NULL){
        release(p->lch);
        free(p);
        release(p->rch);
    }
}

int main(){
    int n, i, j, H, W, N, a[MAX_N], b[MAX_N];
    long long key;
    node *root = NULL;
    
    scanf("%d %d %d", &H, &W, &N);
    for (n=0; n<N; n++) scanf("%*c%d %d", &a[n], &b[n]);
    
    result[0] = (long long)(H-2)*(W-2);
    for (n=0; n<N; n++){
        for (i=-1; i<=1; i++){
            if (a[n]-1+i<1 || H-2<a[n]-1+i) continue;
            for (j=-1; j<=1; j++){
                if (b[n]-1+j<1 || W-2<b[n]-1+j) continue;
                key = (long long)(a[n]-1+i)*(W-1)+b[n]-1+j;
                root = modify(root, a[n]-1+i, b[n]-1+j, key);
            }
        }
    }
    answer(root);
    for (i=0; i<10; i++){
        printf("%lld\n", result[i]);
    }
    release(root);
    return 0;
}