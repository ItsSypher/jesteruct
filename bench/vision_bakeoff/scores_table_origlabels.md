# Vision arbiter bake-off

Shared pages across all models: 56.

| model | pages | errors | valid_json | composite_lenient | composite_shared | ci95_shared | acc_capture | acc_legibility | acc_handwriting | acc_content | acc_script | p50_s | p95_s | usd_per_1k_pages | mean_reasoning_tokens | pareto_usd_per_1k_pages | pareto_p50_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-sol | 60 | 0 | 60/60 | 0.965 | 0.967 | 0.943-0.987 | 0.917 | 0.65 | 0.967 | 0.975 | 1.0 | 4.81 | 7.56 | 5.076 | 93 | True | True |
| google/gemini-3.8-flash | 59 | 1 | 59/59 | 0.944 | 0.946 | 0.920-0.970 | 0.847 | 0.763 | 0.966 | 0.963 | 1.0 | 4.15 | 8.72 | 2.754 | 284 | True | True |
| bytedance-seed/seed-2-1-turbo | 60 | 0 | 60/60 | 0.94 | 0.94 | 0.912-0.967 | 0.833 | 0.717 | 0.95 | 0.975 | 1.0 | 32.59 | 117.34 | 6.967 | 2329 | False | False |
| anthropic/claude-sonnet-5 | 60 | 0 | 60/60 | 0.934 | 0.939 | 0.908-0.968 | 0.85 | 0.733 | 0.933 | 0.969 | 0.983 | 2.96 | 4.28 | 5.234 | 0 | False | True |
| meta/muse-spark-1.3-contributor | 60 | 0 | 60/60 | 0.928 | 0.928 | 0.897-0.956 | 0.767 | 0.683 | 0.967 | 0.978 | 1.0 | 12.11 | 23.4 | 0.402 | 1183 | True | False |
| x-ai/grok-4.7 | 60 | 0 | 60/60 | 0.922 | 0.926 | 0.893-0.955 | 0.783 | 0.7 | 0.967 | 0.969 | 0.967 | 8.43 | 26.46 | 5.429 | 585 | False | False |
| openai/gpt-6-luna-pro | 60 | 0 | 60/60 | 0.922 | 0.922 | 0.888-0.952 | 0.75 | 0.717 | 0.967 | 0.972 | 1.0 | 5.9 | 14.07 | 0.521 | 406 | False | False |
| openai/gpt-6-luna | 60 | 0 | 60/60 | 0.914 | 0.913 | 0.876-0.943 | 0.717 | 0.767 | 0.967 | 0.972 | 1.0 | 3.97 | 7.54 | 0.263 | 130 | True | False |
| ~anthropic/claude-haiku-latest | 60 | 0 | 60/60 | 0.895 | 0.902 | 0.865-0.938 | 0.683 | 0.717 | 0.933 | 0.981 | 0.983 | 2.75 | 3.62 | 2.307 | 0 | False | True |
| deepseek/deepseek-v4.1-flash | 60 | 0 | 60/60 | 0.893 | 0.895 | 0.856-0.932 | 0.817 | 0.667 | 0.983 | 0.972 | 0.8 | 4.63 | 18.52 | 1.531 | 1046 | False | False |
| z-ai/glm-5.3-flash | 60 | 0 | 60/60 | 0.892 | 0.895 | 0.858-0.932 | 0.883 | 0.7 | 0.967 | 0.969 | 0.75 | 6.23 | 30.27 | 0.437 | 408 | False | False |
| xiaomi/mimo-v2.6-flash | 59 | 1 | 59/59 | 0.888 | 0.886 | 0.846-0.923 | 0.831 | 0.729 | 0.949 | 0.992 | 0.78 | 10.65 | 41.02 | 0.278 | 401 | False | False |
| google/gemini-3.5-flash-lite | 60 | 0 | 60/60 | 0.881 | 0.882 | 0.835-0.927 | 0.817 | 0.817 | 0.917 | 0.972 | 0.817 | 1.64 | 2.18 | 0.788 | 0 | False | True |
| inclusionai/ling-3.0-flash-vl | 60 | 0 | 60/60 | 0.871 | 0.871 | 0.831-0.908 | 0.833 | 0.633 | 0.983 | 0.983 | 0.683 | 15.91 | 31.26 | 0.189 | 635 | True | False |
| stepfun/step-3.7-flash | 60 | 0 | 60/60 | 0.846 | 0.849 | 0.807-0.890 | 0.633 | 0.7 | 0.95 | 0.967 | 0.833 | 10.44 | 19.1 | 1.639 | 0 | False | False |
| nex-agi/nex-n2.5-mini | 59 | 1 | 57/59 | 0.804 | 0.809 | 0.750-0.866 | 0.712 | 0.559 | 0.881 | 0.91 | 0.712 | 2.59 | 8.76 | 0.512 | 332 | False | False |
| mistralai/mistral-small-2603 | 30 | 30 | 30/30 | 0.79 | 0.804 | 0.744-0.866 | 0.467 | 0.767 | 0.933 | 0.961 | 0.8 | 1.31 | 1.79 | 0.241 | 0 | False | True |
| qwen/qwen3.8-flash | 59 | 1 | 53/59 | 0.85 | 0.797 | 0.711-0.877 | 0.729 | 0.678 | 0.864 | 0.89 | 0.712 | 7.93 | 12.34 | 0.43 | 511 | False | False |
| qwen/qwen3.8-omni-flash | 59 | 1 | 17/59 | 0.895 | 0.27 | 0.163-0.378 | 0.186 | 0.203 | 0.288 | 0.28 | 0.271 | 15.13 | 41.08 | 0.559 | 637 | False | False |

Low coverage (under 80% of pages answered; composite_shared not comparable): mistralai/mistral-small-2603.

No successful calls: cohere/command-a-plus (60 transport errors).
