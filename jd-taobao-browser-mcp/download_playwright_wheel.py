import pathlib
import time
import urllib.request

url = "https://pypi.tuna.tsinghua.edu.cn/packages/2b/a9/4160c1033c07af98bf841ad079457dd78408a5ee0dd56cbfe50b8b6a1c22/playwright-1.62.0-py3-none-win_amd64.whl"
out = pathlib.Path("..") / "downloads" / "playwright-1.62.0-py3-none-win_amd64.whl"
out.parent.mkdir(exist_ok=True)

print("downloading", url)
with urllib.request.urlopen(url, timeout=60) as response, out.open("wb") as fh:
    total = response.headers.get("content-length")
    print("content-length", total)
    done = 0
    last = time.time()
    while True:
        chunk = response.read(1024 * 256)
        if not chunk:
            break
        fh.write(chunk)
        done += len(chunk)
        now = time.time()
        if now - last >= 2:
            print(done, flush=True)
            last = now

print("saved", out, out.stat().st_size)
