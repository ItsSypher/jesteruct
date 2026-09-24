import pypdfium2 as pdfium, numpy as np, cv2
d=pdfium.PdfDocument("/tmp/jbench/irs.pdf"); a=np.array(d[0].render(scale=120/72).to_pil().convert("RGB"))
cv2.imwrite("/tmp/jbench/p120_digital.png", cv2.cvtColor(a,cv2.COLOR_RGB2BGR))
d2=pdfium.PdfDocument("/tmp/jbench/heron.pdf"); b=np.array(d2[1].render(scale=120/72).to_pil().convert("RGB"))
cv2.imwrite("/tmp/jbench/p120_paper.png", cv2.cvtColor(b,cv2.COLOR_RGB2BGR))
h,w,_=a.shape; H,W=1600,1400
bg=np.zeros((H,W,3),np.uint8); bg[:]=(70,90,110); bg=(bg+np.random.normal(0,8,bg.shape)).clip(0,255).astype(np.uint8)
src=np.float32([[0,0],[w,0],[w,h],[0,h]]); dst=np.float32([[180,140],[1210,210],[1290,1480],[120,1420]])
M=cv2.getPerspectiveTransform(src,dst); warped=cv2.warpPerspective(a,M,(W,H)); mask=cv2.warpPerspective(np.ones((h,w),np.uint8)*255,M,(W,H))
out=bg.copy(); out[mask>0]=warped[mask>0]
grad=np.linspace(0.75,1.05,W)[None,:,None]; out=(out*grad).clip(0,255).astype(np.uint8); out=cv2.GaussianBlur(out,(0,0),1.2)
cv2.imwrite("/tmp/jbench/p_photo.jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 80])
