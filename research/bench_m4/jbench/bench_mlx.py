import time, sys, json, mlx.core as mx
from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config
repo=sys.argv[1]
t=time.perf_counter(); model, processor = load(repo); config = model.config; tl=time.perf_counter()-t
PROMPT=("Classify this document page image. Reply with only a JSON object with keys: "
 "handwriting (none|annotations_only|fields_filled_by_hand|mostly_handwritten|unsure), "
 "capture (digital_render|flatbed_scan|fax|camera_photo|screenshot|unsure), "
 "legibility (clean|mild_issues|hard_to_read|illegible|unsure), "
 "main_content (list from prose,table,form,chart,photo,math,code,letterhead,signature_page), "
 "script (latin|cyrillic|arabic|hebrew|cjk|other|mixed|unsure).")
prompt = apply_chat_template(processor, config, PROMPT, num_images=1)
imgs=["/tmp/jbench/s768_page_digital.jpg","/tmp/jbench/s768_page_scan.jpg","/tmp/jbench/s768_p_photo.jpg"]
print(f"{repo}: load {tl:.1f}s")
for rep in range(2):
  for im in imgs:
    mx.reset_peak_memory()
    t=time.perf_counter(); out = generate(model, processor, prompt, [im], max_tokens=120, temperature=0.0, verbose=False); el=time.perf_counter()-t
    txt = out.text if hasattr(out,"text") else out
    extra = f"prompt_tok {getattr(out,'prompt_tokens','?')} pp {getattr(out,'prompt_tps',0):.0f} tok/s gen {getattr(out,'generation_tokens','?')} tok @ {getattr(out,'generation_tps',0):.0f} tok/s peak {getattr(out,'peak_memory',0):.2f} GB"
    if rep==1: print(f"  {im.split('/')[-1]}: {el:.2f}s | {extra} | {txt.strip().replace(chr(10),' ')[:200]}")
