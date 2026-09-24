# Run-to-run consistency (two independent runs, same inputs)

| model | pages | agree_all_axes | agree_capture | agree_handwriting | agree_content | agree_script | composite_run1 | composite_run2 | acc_when_agree | acc_when_disagree | pages_disagree |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ~anthropic/claude-haiku-latest | 60 | 0.88 | 0.92 | 0.98 | 0.98 | 0.98 | 0.905 | 0.91 | 0.907 | 0.887 | 7 |
| google/gemini-3.5-flash-lite | 59 | 0.85 | 0.98 | 0.98 | 0.97 | 0.92 | 0.913 | 0.909 | 0.931 | 0.815 | 9 |
| google/gemini-3.8-flash | 59 | 0.93 | 0.97 | 1.00 | 0.97 | 1.00 | 0.975 | 0.972 | 0.974 | 0.99 | 4 |
| openai/gpt-6-luna | 60 | 0.90 | 0.95 | 1.00 | 0.95 | 0.97 | 0.944 | 0.935 | 0.944 | 0.951 | 6 |
| openai/gpt-6-luna-pro | 60 | 0.88 | 0.93 | 0.98 | 0.95 | 1.00 | 0.953 | 0.951 | 0.961 | 0.893 | 7 |
