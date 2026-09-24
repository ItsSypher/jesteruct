import httpx, base64, json, time
SCHEMA=json.load(open("/tmp/jbench/schema.json"))
b=base64.b64encode(open("/tmp/jbench/s768_p_photo.jpg","rb").read()).decode()
for i in range(3):
  t=time.perf_counter()
  r=httpx.post("http://localhost:8931/v1/chat/completions",timeout=120,json={"model":"mlx-community/Qwen3-VL-4B-Instruct-4bit","max_tokens":200,"temperature":0,
    "messages":[{"role":"user","content":[{"type":"text","text":"Classify this document page image. Return JSON matching the schema."},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}}]}],
    "response_format":{"type":"json_schema","json_schema":{"name":"page","strict":True,"schema":SCHEMA}}})
  el=time.perf_counter()-t
  j=r.json()
  if "choices" not in j: print(r.status_code, str(j)[:300]); continue
  c=j["choices"][0]["message"]["content"]
  try: json.loads(c); ok=True
  except Exception as e: ok=False
  print(f"{el:.2f}s valid_json={ok} {c[:200]}")
