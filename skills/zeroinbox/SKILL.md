---
name: zeroinbox
description: Run ZEROINBOX sorting and return the PDF report.
user-invocable: true
disable-model-invocation: true
command-dispatch: tool
command-tool: zeroinbox_run
command-arg-mode: raw
---

Run the standalone ZEROINBOX mail sorter.

Default use is safe:

```text
/zeroinbox status
/zeroinbox sort --dry-run --limit 10
/zeroinbox sort --commit --limit 10
```

`--commit` is required before messages are moved.
