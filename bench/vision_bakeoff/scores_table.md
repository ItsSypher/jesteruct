# Vision arbiter bake-off

Shared pages across all models: 56.

| model | pages | errors | valid_json | composite_lenient | composite_shared | ci95_shared | acc_capture | acc_legibility | acc_handwriting | acc_content | acc_script | p50_s | p95_s | usd_per_1k_pages | mean_reasoning_tokens | pareto_usd_per_1k_pages | pareto_p50_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-sol | 60 | 0 | 60/60 | 0.981 | 0.985 | 0.969-0.996 | 0.983 | 0.704 | 0.967 | 0.975 | 1.0 | 4.81 | 7.56 | 5.076 | 93 | True | True |
| google/gemini-3.8-flash | 59 | 1 | 59/59 | 0.979 | 0.979 | 0.962-0.993 | 0.983 | 0.792 | 0.966 | 0.968 | 1.0 | 4.15 | 8.72 | 2.754 | 284 | True | True |
| anthropic/claude-sonnet-5 | 60 | 0 | 60/60 | 0.968 | 0.966 | 0.943-0.987 | 0.983 | 0.796 | 0.933 | 0.972 | 0.983 | 2.96 | 4.28 | 5.234 | 0 | False | True |
| bytedance-seed/seed-2-1-turbo | 60 | 0 | 60/60 | 0.96 | 0.963 | 0.941-0.984 | 0.917 | 0.778 | 0.95 | 0.975 | 1.0 | 32.59 | 117.34 | 6.967 | 2329 | False | False |
| meta/muse-spark-1.3-contributor | 60 | 0 | 60/60 | 0.958 | 0.96 | 0.935-0.981 | 0.883 | 0.741 | 0.967 | 0.983 | 1.0 | 12.11 | 23.4 | 0.402 | 1183 | True | False |
| x-ai/grok-4.7 | 60 | 0 | 60/60 | 0.947 | 0.953 | 0.928-0.975 | 0.883 | 0.759 | 0.967 | 0.972 | 0.967 | 8.43 | 26.46 | 5.429 | 585 | False | False |
| openai/gpt-6-luna-pro | 60 | 0 | 60/60 | 0.949 | 0.95 | 0.920-0.976 | 0.85 | 0.778 | 0.967 | 0.978 | 1.0 | 5.9 | 14.07 | 0.521 | 406 | False | False |
| openai/gpt-6-luna | 60 | 0 | 60/60 | 0.94 | 0.941 | 0.910-0.969 | 0.817 | 0.833 | 0.967 | 0.978 | 1.0 | 3.97 | 7.54 | 0.263 | 130 | True | False |
| deepseek/deepseek-v4.1-flash | 60 | 0 | 60/60 | 0.923 | 0.927 | 0.895-0.958 | 0.933 | 0.741 | 0.983 | 0.975 | 0.8 | 4.63 | 18.52 | 1.531 | 1046 | False | False |
| z-ai/glm-5.3-flash | 60 | 0 | 60/60 | 0.91 | 0.919 | 0.889-0.950 | 0.95 | 0.759 | 0.967 | 0.974 | 0.75 | 6.23 | 30.27 | 0.437 | 408 | False | False |
| ~anthropic/claude-haiku-latest | 60 | 0 | 60/60 | 0.913 | 0.917 | 0.880-0.952 | 0.75 | 0.778 | 0.933 | 0.986 | 0.983 | 2.75 | 3.62 | 2.307 | 0 | False | True |
| google/gemini-3.5-flash-lite | 60 | 0 | 60/60 | 0.91 | 0.914 | 0.877-0.949 | 0.933 | 0.833 | 0.917 | 0.974 | 0.817 | 1.64 | 2.18 | 0.788 | 0 | False | True |
| xiaomi/mimo-v2.6-flash | 59 | 1 | 59/59 | 0.905 | 0.908 | 0.875-0.942 | 0.898 | 0.755 | 0.949 | 0.991 | 0.78 | 10.65 | 41.02 | 0.278 | 401 | False | False |
| inclusionai/ling-3.0-flash-vl | 60 | 0 | 60/60 | 0.901 | 0.907 | 0.874-0.940 | 0.95 | 0.685 | 0.983 | 0.986 | 0.683 | 15.91 | 31.26 | 0.189 | 635 | True | False |
| stepfun/step-3.7-flash | 60 | 0 | 60/60 | 0.872 | 0.877 | 0.835-0.917 | 0.733 | 0.704 | 0.95 | 0.972 | 0.833 | 10.44 | 19.1 | 1.639 | 0 | False | False |
| mistralai/mistral-small-2603 | 30 | 30 | 30/30 | 0.84 | 0.848 | 0.790-0.905 | 0.667 | 0.821 | 0.933 | 0.96 | 0.8 | 1.31 | 1.79 | 0.241 | 0 | False | True |
| nex-agi/nex-n2.5-mini | 59 | 1 | 57/59 | 0.829 | 0.84 | 0.781-0.896 | 0.814 | 0.604 | 0.881 | 0.909 | 0.712 | 2.59 | 8.76 | 0.512 | 332 | False | False |
| qwen/qwen3.8-flash | 59 | 1 | 53/59 | 0.875 | 0.824 | 0.740-0.902 | 0.831 | 0.717 | 0.864 | 0.889 | 0.712 | 7.93 | 12.34 | 0.43 | 511 | False | False |
| qwen/qwen3.8-omni-flash | 59 | 1 | 17/59 | 0.928 | 0.292 | 0.178-0.408 | 0.271 | 0.208 | 0.288 | 0.279 | 0.271 | 15.13 | 41.08 | 0.559 | 637 | False | False |

Low coverage (under 80% of pages answered; composite_shared not comparable): mistralai/mistral-small-2603.

No successful calls: cohere/command-a-plus (60 transport errors).
