#include <stdio.h>
#include <stdlib.h>
#define ll long long
#define rep(i,l,r)for(ll i=(l);i<(r);i++)
#define max(p,q)((p)>(q)?(p):(q))

//辺の情報を個別に持つタイプ
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

typedef struct edge{ll s,g;}E;
typedef struct graph{
	int vcnt,ecnt;
	E  e[100010];//適宜変える
	int id[100010];//適宜変える
}G;

G g;
void readgraph(){
	//適宜変える
	ll n;
	scanf("%lld",&n);
	ll m=0;
	rep(x,0,n){
		int k;
		scanf("%d",&k);
		while(k--){
			ll y;
			scanf("%lld",&y);
			g.e[m].s=x;
			g.e[m].g=y;
			m++;
		}
	}
	g.vcnt=n;
	g.ecnt=m;

	int p=0;
	rep(i,0,g.vcnt){
		while(p<g.ecnt&&g.e[p].s<i)p++;
		g.id[i]=p;
	}
	g.id[g.vcnt]=g.ecnt;//番兵
}




//*
//遅延セグ木ここから
//↓ここを変える
typedef struct sayouso{ll k;}sayouso;
typedef struct atai{ll c,a;}atai;
//↑ここを変える

typedef struct node{sayouso T;atai x;}node;
node *lsegN,*lseg;
ll lsegNUM,lsegk;

//↓ここから変える
sayouso sid={0};
atai aid={0,0};
atai xx(atai x,atai y){
	atai ret;
	ret.c=x.c+y.c;
	ret.a=x.a+y.a;
	return ret;
}
atai Tx(sayouso T,atai x){
	atai ret;
	ret.c=x.c;
	ret.a=T.k*x.c+x.a;
	return ret;
}
sayouso TT(sayouso S,sayouso T){
	sayouso ret;
	ret.k=S.k+T.k;
	return ret;
}
sayouso fT(sayouso T,ll k){
	sayouso ret;
	ret.k=T.k;
	return ret;
}
//↑ここまで変える

//要素数(2ベキ)でこれを呼ぶ
void lseguse(ll n){
	lsegN=(node*)calloc(2*n,sizeof(node));
	lsegNUM=n;
	lseg=lsegN+lsegNUM;
	lsegk=0;while(n/=2)lsegk++;
	rep(i,1,2*lsegNUM){
		lsegN[i].x=aid;
		lsegN[i].T=sid;
	}
}
//lseg[i].xに値を与えてから初期化
void lseginit(){
	for(ll i=lsegNUM-1;i>0;i--)lsegN[i].x=xx(lsegN[2*i].x,lsegN[2*i+1].x);
}
void lsegupdatesub(ll l,ll r,sayouso T,ll i,ll cl,ll cr,ll ck){
	if(l>=r)return;
	//disjointなとき
	if(cr<=l||r<=cl)return;
	//完全に含むとき
	if(l<=cl&&cr<=r){
		lsegN[i].T=TT(T,lsegN[i].T);
		return;
	}
	//どちらでもないとき
	//遅延伝播
	lsegN[2*i  ].T=TT(lsegN[i].T,lsegN[2*i  ].T);
	lsegN[2*i+1].T=TT(lsegN[i].T,lsegN[2*i+1].T);
	//再帰的に更新
	ll cm=(cl+cr)/2;
	lsegupdatesub(l,r,T,2*i  ,cl,cm,ck-1);
	lsegupdatesub(l,r,T,2*i+1,cm,cr,ck-1);
	//自身のnodeを更新
	lsegN[i].x=xx(Tx(fT(lsegN[2*i].T,ck-1),lsegN[2*i].x),Tx(fT(lsegN[2*i+1].T,ck-1),lsegN[2*i+1].x));
	lsegN[i].T=sid;
}
void lsegupdate(ll l,ll r,sayouso T){lsegupdatesub(l,r,T,1,0,lsegNUM,lsegk);}
atai lsegcalcsub(ll l,ll r,ll i,ll cl,ll cr,ll ck){
	if(l>=r)return aid;
	//完全に含むとき
	if(l<=cl&&cr<=r)return Tx(fT(lsegN[i].T,ck),lsegN[i].x);

	ll cm=(cl+cr)/2;
	//遅延伝播(変更はないので配るだけで良い)
	lsegN[2*i  ].T=TT(lsegN[i].T,lsegN[2*i  ].T);
	lsegN[2*i+1].T=TT(lsegN[i].T,lsegN[2*i+1].T);
	lsegN[i].x=Tx(fT(lsegN[i].T,ck),lsegN[i].x);
	lsegN[i].T=sid;

	//左側だけ
	if(r<=cm)return lsegcalcsub(l,r,2*i  ,cl,cm,ck-1);
	//右側だけ
	if(cm<=l)return lsegcalcsub(l,r,2*i+1,cm,cr,ck-1);
	//両方
	return xx(lsegcalcsub(l,r,2*i,cl,cm,ck-1),lsegcalcsub(l,r,2*i+1,cm,cr,ck-1));
}
atai lsegcalc(ll l,ll r){return lsegcalcsub(l,r,1,0,lsegNUM,lsegk);}
//遅延セグ木ここまで
//*/




#define VCNT 100000
ll ein[VCNT+10],eout[VCNT+10];
ll vin[VCNT+10],vout[VCNT+10];
ll ETe[2*VCNT+10];
ll cnt=0;
#undef VCNT
void ETdfs(int v){
	vin[v]=cnt;
	rep(i,g.id[v],g.id[v+1]){
		ein[i]=cnt;
		ETe[cnt]=i;
		cnt++;
		ETdfs(g.e[i].g);
		eout[i]=cnt;
		ETe[cnt]=i+g.ecnt;
		cnt++;
	}
	vout[v]=cnt;
}

int main(){
	readgraph();
	ETdfs(0);
	lseguse(1<<18);
	rep(i,0,g.ecnt)lseg[ein[i]].x.c=1;
	rep(i,0,g.ecnt)lseg[eout[i]].x.c=-1;
	lseginit();
	int q;
	scanf("%d",&q);
	while(q--){
		int t;
		scanf("%d",&t);
		if(t){
			int x;
			scanf("%d",&x);
			printf("%lld\n",lsegcalc(0,vin[x]).a);
		}else{
			int x,c;
			scanf("%d%d",&x,&c);
			sayouso T={c};
			lsegupdate(vin[x]-1,vin[x],T);
			lsegupdate(vout[x],vout[x]+1,T);
		}
	}
}
