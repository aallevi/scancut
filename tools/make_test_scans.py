# scansioni finte per provare che il codice nuovo dia gli stessi byte del vecchio (non la qualita dei bordi)
# uso: cd <cartella vuota> && python3 -I ~/Scans/.scancut/tools/make_test_scans.py
import numpy as np, cv2, sys
from PIL import Image
rng=np.random.default_rng(1)
def scan(bg, sheets, name, dpi=300):
    W,H=int(216/25.4*dpi), int(297/25.4*dpi)
    im=np.full((H,W,3), bg, np.float32)+rng.normal(0,1.5,(H,W,3))
    for (cx,cy,w,h,ang,col,holes) in sheets:
        m=np.zeros((H,W),np.uint8)
        box=cv2.boxPoints(((cx*W,cy*H),(w*dpi/25.4,h*dpi/25.4),ang)).astype(np.int32)
        cv2.fillPoly(m,[box],1)
        sh=cv2.GaussianBlur(cv2.dilate(m,np.ones((5,5))).astype(np.float32),(0,0),2)
        im*= (1-0.12*sh*(1-m))[...,None]
        im[m>0]=np.array(col,np.float32)+rng.normal(0,2,((m>0).sum(),3))
        for k in range(30):
            p=rng.integers(0,len(box)); x0,y0=box.mean(0).astype(int)
            cv2.line(im,(x0+int(rng.normal(0,200)),y0+int(rng.normal(0,300))),(x0+int(rng.normal(0,200)),y0+int(rng.normal(0,300))),(60,60,70),2)
        for hy in holes:
            c=(box.mean(0)+np.array([-w*dpi/25.4/2+12*dpi/25.4, hy*dpi/25.4])).astype(int)
            cv2.circle(im,tuple(int(v) for v in c),int(3*dpi/25.4),bg,-1)
    Image.fromarray(np.clip(im,0,255).astype(np.uint8)).save(name, dpi=(dpi,dpi))
scan((246,246,244),[(0.5,0.5,180,250,3,(238,232,215),[])],'ivory 1.png')
scan((128,128,126),[(0.3,0.5,90,200,0,(250,250,248),[-40,40]),(0.73,0.5,95,200,0,(225,235,250),[])],'card 1.png')
scan((247,247,246),[(0.5,0.45,150,200,-2,(246,246,244),[])],'white 1.png')
