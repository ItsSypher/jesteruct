# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
import httpx, base64, json, time, sys
sys.argv=['x']; exec(open('vlmbench.py').read().split('def main')[0])
b64 = base64.b64encode(open('imgs/vlm_paper1_scan.jpg','rb').read()).decode()
for stream in (False,):
  p = payload("mlx-community/Qwen3-VL-4B-Instruct-4bit", "imgs/vlm_paper1_scan.jpg", {"stream": stream})
  p.pop("stream_options")
  t=time.time(); r = httpx.post("http://127.0.0.1:8089/v1/chat/completions", json=p, timeout=300); 
  j=r.json(); print(round(time.time()-t,2), json.dumps(j)[:1500])
