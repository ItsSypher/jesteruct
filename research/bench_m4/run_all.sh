#!/bin/zsh
cd /tmp/pdfbench
for i in {1..240}; do pgrep -f "jbench|jstbench|b33a4syay" >/dev/null || break; sleep 5; done
# wait for downloads to finish
for i in {1..360}; do pgrep -f "snapshot_download" >/dev/null || break; sleep 5; done
echo "start $(date +%T); other bench procs: $(pgrep -fl 'jbench|jstbench' | wc -l)"
(cd layout && uv run lbench.py 2>&1 | grep -vE "Installed|Warning|warn|Fetching" ) > layout_results.txt
(cd layout && uv run onnxbench.py 2>&1 | grep -vE "Installed|Fetching") >> layout_results.txt
echo "layout done $(date +%T); other bench procs: $(pgrep -fl 'jbench|jstbench' | wc -l)" >> layout_results.txt
cd mlx && ./run_local.sh Qwen3-VL-2B-Instruct-4bit Qwen3-VL-4B-Instruct-4bit Qwen3-VL-4B-Instruct-8bit Qwen3-VL-8B-Instruct-4bit Qwen3.5-4B-4bit MiniCPM-V-4.6-4bit gemma-4-e4b-it-4bit SmolVLM2-2.2B-Instruct-mlx > local_results.txt 2>&1
echo "vlm done $(date +%T); other bench procs: $(pgrep -fl 'jbench|jstbench' | wc -l)" >> local_results.txt
