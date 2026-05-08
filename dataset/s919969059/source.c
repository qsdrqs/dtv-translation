#include<stdio.h>
#include<stdlib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <float.h>

int del_Recipies(int del,int count,int n,int m,int p[],int Recipies[500][500]);

int main()
{
	int n,m,Recipies[500][500]={0},MAX[500],min_del_Recipies,c,flag,*p,count;
	
	while(1)
	{
		scanf("%d %d",&n,&m);
		if(n==0&&m==0) break;
		min_del_Recipies=-1;
		for(int i=0;i<m;i++) MAX[i]=0;
		for(int i=0;i<n;i++)
		{
			for(int t=0;t<m;)
			{
				Recipies[i][t]=getchar();
				if(Recipies[i][t] != '\n'&& Recipies[i][t] != ' ')
				{
					Recipies[i][t]-='0';
					MAX[t]+=Recipies[i][t];
					t++;
				}
			}
		}
		flag=1;
		//作る際に必要な材料数がすべての材料で2で割り切れたなら、その時のレシピ数になる
		for(int t=0;t<m;t++)
		{
			if(MAX[t]%2)
			{
				flag=0;
				break;
			}
		}
		if(flag) min_del_Recipies=0;
		else
		{
			p=(int*)malloc(m*sizeof(int));
			//すべて作った時に必要な材料からレシピを減らしていく
			//減らしていく数を順に増やしていき、その減らす数の時のすべての減らし方を試す
			
			for(int del=1;del<n;del++)//何個引くか del個 引いた個数 count
			{
				for(int i=0;i<m;i++) p[i]=MAX[i];
				count=0;
				flag=del_Recipies(del,count,n,m,p,Recipies);//何個引くか del個 引いた個数 count
				//del個減らしたときにすべての材料が2で割り切れるものがあったら 1を返す なかったら 0を返す
				if(flag)
				{
					min_del_Recipies = del;//delで割り切れたとき
					break;
				}
			}
			if(min_del_Recipies==-1)min_del_Recipies=n;//どれも割り切れなかったとき
			free(p);
		}
		printf("%d\n",n-min_del_Recipies);//全体から割り切れるまでに引いた個数を引くと求まる
	}
	return 0;
}

int del_Recipies(int del,int count,int n,int m,int p[],int Recipies[500][500])
{
	//引く個数=del 引いた個数=count何種類目 i
	int flag=1;
	for(;count<n && n-count>=del;count++)
	{
		
		if(del==1)
		{
			flag=1;
			for(int t=0;t<m;t++)
			{
				p[t]-=Recipies[count][t];
				if(p[t]%2!=0)
				{
					flag=0;
					p[t]+=Recipies[count][t];
					break;
				}
				p[t] += Recipies[count][t];
			}
			if(flag) return 1;
			else continue;
		}
		else 
		{
			//残りの引く個数が1になるまで再起
			//pから今回引くRecipiesを引いてから次に渡す
			for(int t=0;t<m;t++) p[t]-=Recipies[count][t];
			//引く個数delを一つ減らす　引いた個数countを一つ増やす
			if(del_Recipies(del-1,count+1,n,m,p,Recipies)) return 1;
			for (int t = 0; t<m; t++) p[t] += Recipies[count][t];
		}
		
	}
	return 0;
}
