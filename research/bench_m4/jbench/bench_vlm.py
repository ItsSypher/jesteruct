import os, time, json, base64, statistics as st, httpx, sys
KEY=os.environ["OPENROUTER_API_KEY"]
SCHEMA={"type":"object","additionalProperties":False,"required":["handwriting","capture","legibility","main_content","script"],"properties":{
 "handwriting":{"type":"string","enum":["none","annotations_only","fields_filled_by_hand","mostly_handwritten","unsure"]},
 "capture":{"type":"string","enum":["digital_render","flatbed_scan","fax","camera_photo","screenshot","unsure"]},
 "legibility":{"type":"string","enum":["clean","mild_issues","hard_to_read","illegible","unsure"]},
 "main_content":{"type":"array","items":{"type":"string","enum":["prose","table","form","chart","photo","math","code","letterhead","signature_page"]}},
 "script":{"type":"string","enum":["latin","cyrillic","arabic","hebrew","cjk","other","mixed","unsure"]}}}
PROMPT="Classify this document page image. Answer only from what is visible. Return JSON matching the schema."
imgs={k:base64.b64encode(open(f"/tmp/jbench/page_{k}.jpg","rb").read()).decode() for k in ["digital","scan","photo"]}
models=sys.argv[1:]
cli=httpx.Client(timeout=120, http2=False)
for spec in models:
  m,eff=(spec.split('=')+['off'])[:2]
  rows=[]
  for rep in range(3):
    for k,b in imgs.items():
      body={"model":m,"stream":True,"max_tokens":400,"temperature":0,
        "messages":[{"role":"user","content":[{"type":"text","text":PROMPT},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}}]}],
        "response_format":{"type":"json_schema","json_schema":{"name":"page","strict":True,"schema":SCHEMA}},
        "usage":{"include":True}}
      if eff=="off": body["reasoning"]={"enabled":False}
      elif eff!="default": body["reasoning"]={"effort":eff}
      t0=time.perf_counter(); ttft=None; txt=""; usage=None; prov=None; err=None
      try:
        with cli.stream("POST","https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":f"Bearer {KEY}"},json=body) as r:
          if r.status_code!=200: err=f"{r.status_code} {r.read()[:200]}"
          else:
            for line in r.iter_lines():
              if not line.startswith("data: ") or line=="data: [DONE]": continue
              j=json.loads(line[6:]); prov=j.get("provider",prov)
              if j.get("usage"): usage=j["usage"]
              for c in j.get("choices",[]):
                d=c.get("delta",{}).get("content")
                if d:
                  if ttft is None: ttft=time.perf_counter()-t0
                  txt+=d
      except Exception as e: err=str(e)[:200]
      tot=time.perf_counter()-t0
      rows.append(dict(k=k,ttft=ttft,tot=tot,txt=txt,usage=usage,prov=prov,err=err))
  ok=[r for r in rows if not r["err"] and r["ttft"]]
  if not ok: print(m,"FAILED",rows[0]["err"]); continue
  u=ok[-1]["usage"] or {}
  print(f"{m} (reasoning={eff}) [{','.join(sorted({str(r['prov']) for r in ok}))}] n={len(ok)}/{len(rows)} TTFT med {st.median([r['ttft'] for r in ok]):.2f}s total med {st.median([r['tot'] for r in ok]):.2f}s max {max(r['tot'] for r in ok):.2f}s | in_tok {u.get('prompt_tokens')} out_tok {u.get('completion_tokens')} cost ${u.get('cost')}")
  for k in ["digital","scan","photo"]:
    t=[r['txt'] for r in ok if r['k']==k]
    def cj(x):
      try: return json.dumps(json.loads(x))
      except Exception: return 'INVALID_JSON: '+x[:120].replace(chr(10),' ')
    print(f"   {k}: {cj(t[0]) if t else '-'}  valid={sum(1 for x in t if not cj(x).startswith('INVALID'))}/{len(t)}")
