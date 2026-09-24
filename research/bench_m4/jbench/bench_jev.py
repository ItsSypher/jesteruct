import os, time, httpx, statistics as st, json
KEY=os.environ["OPENROUTER_API_KEY"]
body={"model":"typesafe/jev-1.13","state":{"page_evidence":"Text layer: present on most of the page. Earlier OCR layer: yes. Scan quality: mild blur, high contrast. Columns: two. Language guess: English, high confidence.",
 "page_text_sample":"Form 1040 U.S. Individual Income Tax Return 2025. Filing Status. Check only one box. Single Married filing jointly Married filing separately (MFS) Head of household (HOH) Qualifying surviving spouse (QSS). Your first name and middle initial. Last name. Your social security number."},
 "questions":{"text_layer":{"type":"choice","instructions":"Judge only `page_text_sample`. Is it usable text from this page?","criteria":{"trusted":"Readable words and sentences in a real language.","untrusted":"Mostly readable but with frequent misspellings or merged columns typical of poor OCR.","garbled":"Mostly symbols or broken encoding.","insufficient":"Too little text to judge."}},
  "is_separator":{"type":"noul","instructions":"This page is a fax cover sheet, blank separator, or scanning slip with no document content."}}}
cli=httpx.Client(timeout=60)
ts=[]; last=None
for i in range(12):
  t=time.perf_counter(); r=cli.post("https://openrouter.ai/api/alpha/decisions",headers={"Authorization":f"Bearer {KEY}"},json=body); ts.append(time.perf_counter()-t)
  last=r
  if r.status_code!=200: print(r.status_code, r.text[:300]); break
print("jev via OpenRouter from FI (warm conn): median %.3fs min %.3fs max %.3fs n=%d"%(st.median(ts[1:]),min(ts[1:]),max(ts[1:]),len(ts)-1), "first(cold) %.3fs"%ts[0])
j=last.json(); print(json.dumps(j)[:700])
