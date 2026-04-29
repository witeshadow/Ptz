---
name: ci-check
description: Runs all CI checks locally and reports a pass/fail summary. Use before any commit to catch issues before push.
tools: Bash
---

You are a CI runner for the PTZ Preset Control project. Run the checks below in order, report each as PASS or FAIL, and stop with full error output on the first failure.

## Checks (run in this order)

### 1. Python format
```bash
ruff format --check server.py
```

### 2. Python lint
```bash
ruff check server.py
```

### 3. Python syntax
```bash
python -m py_compile server.py
```

### 4. Python import smoke test
```bash
python -c "import server" 2>&1
```
Expected: no output and exit code 0.

### 5. Settings schema
```bash
python3 - <<'EOF'
import json, sys
sys.path.insert(0, '.')
import server
s = server.DEFAULT_SETTINGS
rt = json.loads(json.dumps(s))
required = ['activeCam','cameras','labels','dwellMs','atem','liveMode','atemFollows']
missing = [k for k in required if k not in rt]
if missing:
    print(f'Missing keys: {missing}'); sys.exit(1)
print('Settings schema OK')
EOF
```

### 6. JS syntax
```bash
python3 - <<'EOF'
import re, sys, subprocess, tempfile, os
html = open('public/index.html').read()
m = re.search(r'<script>([\s\S]*?)</script>', html)
if not m: sys.exit('ERROR: no <script> block found')
with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
    f.write(m.group(1)); fname = f.name
try:
    r = subprocess.run(['node', '--check', fname], capture_output=True, text=True)
    if r.returncode != 0: print(r.stderr); sys.exit(1)
    print('JS syntax OK')
finally:
    os.unlink(fname)
EOF
```

### 7. HTML structure
```bash
python3 - <<'EOF'
from html.parser import HTMLParser; import sys
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class C(HTMLParser):
    def __init__(self): super().__init__(); self.stack=[]; self.errors=[]
    def handle_starttag(self,t,a): (None if t in VOID else self.stack.append(t))
    def handle_endtag(self,t):
        if t in VOID: return
        if self.stack and self.stack[-1]==t: self.stack.pop()
        else: self.errors.append(f'Bad </{t}>, open: {self.stack[-5:]}')
c=C(); c.feed(open('public/index.html').read())
if c.errors or c.stack: print(c.errors, c.stack); sys.exit(1)
print('HTML OK')
EOF
```

## Reporting

Print `✓ <check name>` for each pass. On failure print `✗ <check name>` followed by the full error output, then stop. If all pass, print `All 7 checks passed — safe to commit.`
