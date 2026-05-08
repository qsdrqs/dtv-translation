#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <limits.h>
#include <math.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef int64_t ll;
typedef uint64_t ull;
int acs(const void *a, const void *b){return *(int*)a - *(int*)b;} /* 1,2,3,4.. */
int des(const void *a, const void *b){return *(int*)b - *(int*)a;} /* 8,7,6,5.. */
#define min(a,b) (a < b ? a: b)
#define max(a,b) (a > b ? a: b)

#define MAXN (100000)
#define MOD (1000000007)

//グラフ
#define MAXV (MAXN)
int Gv;
typedef struct edge
{
    int to;
    ll cost;
    int color;
    struct edge* next;
}edge;

edge* Ge[MAXV]; //vから出てる有向辺
int Gd[MAXV]; //vの次数

// vは頂点数、指定するときは0～(v-1)
void Ginit(int v)
{
    Gv = v;
}

void Gadd(int v, int to, ll cost, int color)
{
    edge* e = malloc(sizeof(edge));
    e->to = to;
    e->cost = cost;
    e->color = color;
    e->next = Ge[v];
    Ge[v] = e;
    Gd[v]++;
}

// 0を根としたLCA
ll Gdep[MAXV]; //根からの深さ
ll Gcost[MAXV]; //根からのcost和
ll Gpar[MAXV][30]; //2^i個上の親
ll Groute[MAXV];
//実行時は GinitLCA(0,0,0,-1)
void GinitLCA(int v, int d,ll c,int p)
{
    Groute[d] = v;
    Gdep[v] = d;
    Gcost[v] = c;
    for(ll i=0;i<30;i++)
    {
        if((1<<i) > d) Gpar[v][i] = -1;
        else Gpar[v][i] = Groute[d-(1<<i)];
    }
    edge*e = Ge[v];
    while(e!=NULL)
    {
        if(e->to!=p) GinitLCA(e->to,d+1,c+(e->cost),v);
        e = e->next;
    }
}

int Glca(int u,int v)
{
    if(u==v) return u;
    if(Gdep[u] != Gdep[v]) 
    {
        int a = Gdep[u] >  Gdep[v] ? u : v;
        int b = Gdep[u] <  Gdep[v] ? u : v;
        int d = Gdep[a] - Gdep[b];
        int i = 0;
        while(d!=1){i++;d>>=1;}
        return Glca(Gpar[a][i],b);
    }
    for(int i=30-1;i>=0;i--)
    {
        if(Gpar[u][i]!=Gpar[v][i])
        {
            return Glca(Gpar[u][i],Gpar[v][i]);
        }
    }
    return Gpar[u][0];
}

typedef struct list
{
    int val;
    struct list* next;
}list;


int x[MAXN];
int y[MAXN];
int u[MAXN];
int v[MAXN];
ll ans[MAXN];

list* vq[MAXN];
list* cq[MAXN];

int cn[MAXN];
ll cs[MAXN];

void dfs(int v,int p)
{
    list* l = cq[v];
    while(l!=NULL)
    {
        ans[l->val] -= (cn[x[l->val]]*y[l->val]  - cs[x[l->val]])*2;
        l = l->next;
    }
    l = vq[v];
    while(l!=NULL)
    {
        ans[l->val] += cn[x[l->val]]*y[l->val]  - cs[x[l->val]];
        l = l->next;
    }

    edge* e = Ge[v];
    while(e!=NULL)
    {
        if(e->to!=p)
        {
            cn[e->color]++;
            cs[e->color]+= e->cost;
            dfs(e->to,v);
            cn[e->color]--;
            cs[e->color]-= e->cost;
        }
        e = e->next;
    }
}

int main(void)
{
    ll n,q;
    scanf("%ld %ld",&n,&q);

    for(int i=0;i<n-1;i++)
    {
        int a,b,c,d;
        scanf("%d %d %d %d",&a,&b,&c,&d);
        a--; b--;
        Gadd(a,b,d,c);
        Gadd(b,a,d,c);
    }
    GinitLCA(0,0,0,-1);
    for(int i=0;i<q;i++)
    {
        scanf("%d %d %d %d",&(x[i]),&(y[i]),&(u[i]),&(v[i]));
        u[i]--;v[i]--;
        int l = Glca(u[i],v[i]);
        ans[i] = Gcost[u[i]] + Gcost[v[i]] - (Gcost[l]*2);
        list* vl1 = malloc(sizeof(list));
        vl1->val = i;
        list* vl2 = malloc(sizeof(list));
        vl2->val = i;
        list* cl = malloc(sizeof(list));
        cl->val = i;
        vl1->next = vq[u[i]];
        vq[u[i]] = vl1;
        vl2->next = vq[v[i]];
        vq[v[i]] = vl2;
        cl->next = cq[l];
        cq[l] = cl;
    }
    dfs(0,-1);
    for(int i=0;i<q;i++)
    {
        printf("%ld\n",ans[i]);
    }

    return 0;
}
