#include <stdio.h>
#include <string.h>
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

int i,j,n,a[300000],b[300000],c[300000];
void qt(int l,int r)
{
    int i,j,m,p;
    i=l; j=r;
    m=a[(l+r)/2];
    while (i<=j)
    {
        while (a[i]<m) i++;
        while (a[j]>m) j--;
        if (i<=j)
        {
            p=a[i];a[i]=a[j]; a[j]=p;
            p=b[i]; b[i]=b[j]; b[j]=p;
            i++; j--;
        }
    }
if (i<r) qt(i,r);
if (l<j) qt(l,j);
}

int main()
{
    scanf("%d",&n);
    for (i=1;i<=n;i++)
    {
        scanf("%d",&a[i]);
        b[i]=i;
    }
    qt(1,n);
    for (i=1;i<=n;i++)
        c[b[i]]=i;
    for (i=1;i<=n;i++)
    {
        if (c[i]<=(n/2)) printf("%d\n",a[(1+n)/2+1]); else printf("%d\n",a[(1+n)/2]);
    }
    return(0);
}
