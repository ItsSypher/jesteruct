import pypdfium2 as pdfium, numpy as np, cv2
from PIL import Image
d=pdfium.PdfDocument("/tmp/jbench/irs.pdf"); im=d[0].render(scale=150/72, grayscale=True).to_pil()
im.thumbnail((1024,1024)); im.save("/tmp/jbench/page_digital.jpg", quality=85)
a=np.array(d[0].render(scale=150/72, grayscale=True).to_pil()).astype(np.float32)
h,w=a.shape; M=cv2.getRotationMatrix2D((w/2,h/2),2.3,1.0); a=cv2.warpAffine(a,M,(w,h),borderValue=235)
a=cv2.GaussianBlur(a,(0,0),1.6); a=a*0.8+30+np.random.normal(0,12,a.shape); a=np.clip(a,0,255).astype(np.uint8)
s=Image.fromarray(a); s.thumbnail((1024,1024)); s.save("/tmp/jbench/page_scan.jpg", quality=60)
print(Image.open("/tmp/jbench/page_digital.jpg").size)
