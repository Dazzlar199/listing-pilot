import os, re
def load_env(path=".env"):
    if not os.path.exists(path): return
    for line in open(path):
        m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*)\s*$", line)
        if m and m.group(2) and not os.environ.get(m.group(1)):
            os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")
