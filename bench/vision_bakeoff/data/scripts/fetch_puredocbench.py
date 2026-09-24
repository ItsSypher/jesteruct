"""
Fetch the specific PureDocBench clean/digital/real images we need directly
from the remote split tar archive, without downloading the full ~35GB file.

Resumable: writes progress to state.json next to OUT_DIR so a killed/timed-out
run can continue roughly where it left off.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from pdb_tar_reader import RemoteSplitTar, TarWalker  # noqa: E402

ROOT = "/Users/kavy/Code/Projects/jesteruct/bench/vision_bakeoff/data"
OUT_DIR = os.path.join(ROOT, "raw", "puredocbench_images")
STATE_PATH = os.path.join(OUT_DIR, "_state.json")
os.makedirs(OUT_DIR, exist_ok=True)

PREFIX = "puredocbench-v1.0/images/"

# (page_id, clean_rel, real_rel) -- digital_rel always equals clean_rel in the
# release manifest (same filename, different top-level track directory).
TARGETS = [
    ("01_academic/01_journal_paper/academic_paper_017_数学超密集双栏",
     "01_academic/01_journal_paper/academic_paper_017_数学超密集双栏.png",
     "01_academic/01_journal_paper/academic_paper_017_数学超密集双栏__real_screen_photography.png"),
    ("01_academic/01_journal_paper/academic_paper_005_计算机学报_图神经网络",
     "01_academic/01_journal_paper/academic_paper_005_计算机学报_图神经网络.png",
     "01_academic/01_journal_paper/academic_paper_005_计算机学报_图神经网络__real_phone_flat_normal_top.png"),
    ("01_academic/01_journal_paper/academic_paper_001_JACS_催化反应动力学",
     "01_academic/01_journal_paper/academic_paper_001_JACS_催化反应动力学.png",
     "01_academic/01_journal_paper/academic_paper_001_JACS_催化反应动力学__real_screen_na_screen_screen.png"),
    ("01_academic/02_thesis/thesis_003_博士论文_量子信息",
     "01_academic/02_thesis/thesis_003_博士论文_量子信息.png",
     "01_academic/02_thesis/thesis_003_博士论文_量子信息__real_phone_flat_normal_top.png"),
    ("01_academic/03_technical_report/technical_report_011_银行风控报告",
     "01_academic/03_technical_report/technical_report_011_银行风控报告.png",
     "01_academic/03_technical_report/technical_report_011_银行风控报告__real_phone_flat_normal_top.png"),
    ("01_academic/04_patent/patent_004_发明专利_说明书摘要",
     "01_academic/04_patent/patent_004_发明专利_说明书摘要.png",
     "01_academic/04_patent/patent_004_发明专利_说明书摘要__real_screenshot_na_na_na.jpg"),
    ("02_education/06_lab_report/lab_report_001_杨氏模量测定实验",
     "02_education/06_lab_report/lab_report_001_杨氏模量测定实验.png",
     "02_education/06_lab_report/lab_report_001_杨氏模量测定实验__real_screenshot_na_na_na.png"),
    ("02_education/06_lab_report/lab_report_003_Spectrophotometric_Iron_EN",
     "02_education/06_lab_report/lab_report_003_Spectrophotometric_Iron_EN.png",
     "02_education/06_lab_report/lab_report_003_Spectrophotometric_Iron_EN__real_phone_flat_normal_top.png"),
]

# Build the wanted-path -> local-save-path map.
WANTED = {}
for page_id, clean_rel, real_rel in TARGETS:
    WANTED[PREFIX + "clean/" + clean_rel] = os.path.join(OUT_DIR, "clean", clean_rel)
    WANTED[PREFIX + "digital_degraded/" + clean_rel] = os.path.join(OUT_DIR, "digital_degraded", clean_rel)
    WANTED[PREFIX + "real_degraded/" + real_rel] = os.path.join(OUT_DIR, "real_degraded", real_rel)

ALREADY_HAVE_CLEAN_LOCALLY = {  # extracted earlier from the 160MB head buffer
    PREFIX + "clean/01_academic/01_journal_paper/academic_paper_017_数学超密集双栏.png",
    PREFIX + "clean/01_academic/01_journal_paper/academic_paper_005_计算机学报_图神经网络.png",
    PREFIX + "clean/01_academic/01_journal_paper/academic_paper_001_JACS_催化反应动力学.png",
    PREFIX + "clean/01_academic/02_thesis/thesis_003_博士论文_量子信息.png",
    PREFIX + "clean/01_academic/03_technical_report/technical_report_011_银行风控报告.png",
    PREFIX + "clean/01_academic/04_patent/patent_004_发明专利_说明书摘要.png",
}


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"cursor": None, "found": [], "requests_made": 0}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)


def main():
    state = load_state()
    found = set(state["found"])
    remaining = {k: v for k, v in WANTED.items() if k not in found and k not in ALREADY_HAVE_CLEAN_LOCALLY}
    for k in WANTED:
        if k in ALREADY_HAVE_CLEAN_LOCALLY:
            found.add(k)

    print(f"[{time.strftime('%H:%M:%S')}] Need {len(remaining)} more files. Already have {len(found)}.")
    if not remaining:
        print("Nothing to do.")
        return

    tar = RemoteSplitTar()
    walker = TarWalker(tar)
    walker.cursor = state["cursor"] if state["cursor"] is not None else 65171968  # start of images/

    scanned = 0
    t_start = time.time()
    while remaining:
        entry = walker.next_entry()
        if entry is None:
            print("Reached EOF before finding all targets! Missing:", remaining.keys())
            break
        name, size, offset = entry
        scanned += 1
        if name in remaining:
            data = walker.fetch_data(entry)
            outpath = remaining[name]
            os.makedirs(os.path.dirname(outpath), exist_ok=True)
            with open(outpath, "wb") as f:
                f.write(data)
            found.add(name)
            del remaining[name]
            print(f"  [{time.strftime('%H:%M:%S')}] GOT {name} ({size} bytes) -> {outpath}; {len(remaining)} left")

        if scanned % 100 == 0:
            elapsed = time.time() - t_start
            print(f"  ... scanned {scanned} entries, cursor={walker.cursor}, "
                  f"requests={tar.requests_made}, elapsed={elapsed:.0f}s, remaining={len(remaining)}")
            state["cursor"] = walker.cursor
            state["found"] = sorted(found)
            state["requests_made"] = tar.requests_made
            save_state(state)

    state["cursor"] = walker.cursor
    state["found"] = sorted(found)
    state["requests_made"] = tar.requests_made
    save_state(state)
    print(f"[{time.strftime('%H:%M:%S')}] Done. found={len(found)}/{len(WANTED)} total_requests={tar.requests_made}")


if __name__ == "__main__":
    main()
