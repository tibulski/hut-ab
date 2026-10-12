import re, numpy as np, json
rows=open(__import__('os').path.join(__import__('os').path.dirname(__file__),'..','data','ufz_grid_2026-10-10_rle.txt')).read().strip().split('|')
G=np.array([list(''.join(c*int(n or 1) for c,n in re.findall(r'(\D)(\d*)',r))) for r in rows])
merc=lambda la: np.degrees(np.log(np.tan(np.pi/4+np.radians(la)/2)))
ty=np.array([55.5,264.5,471.5,676.5,878.5]); tl=np.array([53.5,53,52.5,52,51.5])
b,a=np.polyfit(merc(tl),ty,1)
def lat(y):
    m=(y-a)/b; return np.degrees(2*np.arctan(np.exp(np.radians(m)))-np.pi/2)
lon=lambda x: 11+(x-142.5)/251.25
X=693+4*np.arange(G.shape[1]); Y=150+4*np.arange(G.shape[0])
LON=lon(X); LAT=lat(Y)
dlon=4/251.25; dlat=[abs(lat(y-2)-lat(y+2)) for y in Y]
if __name__=='__main__':
    print('resid',np.round(ty-(a+b*merc(tl)),2))
    print(LON[0],LON[-1],LAT[0],LAT[-1])
    from scipy import ndimage
    for cls in ['G','W','H']:
        lab,n=ndimage.label(G==cls)
        for i in range(1,n+1):
            yy,xx=np.where(lab==i)
            if len(yy)<3: continue
            print(cls,len(yy),'cells', round(LAT[yy].mean(),3),round(LON[xx].mean(),3),'lat',round(LAT[yy].min(),3),round(LAT[yy].max(),3),'lon',round(LON[xx].min(),3),round(LON[xx].max(),3))
