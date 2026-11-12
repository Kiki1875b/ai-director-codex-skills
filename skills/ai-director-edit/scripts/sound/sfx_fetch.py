"""Pick single sound files out of the Sonniss GDC bundle zips on the your.org mirror without downloading
whole parts. Reads each zip's central directory with HTTP range requests, then fetches only the members asked for.

  python sfx_fetch.py index                 # write sfx_index.tsv next to this script (year, part url, member, size)
  python sfx_fetch.py find "rain.*plastic"  # search the index (case-insensitive regex)
  python sfx_fetch.py get --story stories/<slug> "<member>" ...
                                            # extract members (exact names from the index) to <story>/media/audio/sfx/src/
  python sfx_fetch.py get --dest DIR "<member>" ...   # or to DIR/<year>/ directly

Licence: Sonniss GDC bundle licence (royalty-free media production, no attribution, no AI/ML training).
"""
import csv, io, os, re, sys, urllib.parse, urllib.request, zipfile

MIRROR = "https://ftpmirror.your.org/pub/misc/"
YEARS = ["sonniss2016", "sonniss2017", "sonniss2018", "sonniss2019", "sonniss2020"]
HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "sfx_index.tsv")
UA = {"User-Agent": "sfx-fetch/1.0"}


class HTTPRangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests, with a small read-ahead cache."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, method="HEAD", headers=UA)
        with urllib.request.urlopen(req) as r:
            self.size = int(r.headers["Content-Length"])
        self.buf_start, self.buf = 0, b""

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size)
        if not (self.buf_start <= self.pos and end <= self.buf_start + len(self.buf)):
            want_end = min(max(end, self.pos + (1 << 20)), self.size)   # read ahead 1 MB
            req = urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={self.pos}-{want_end - 1}"})
            with urllib.request.urlopen(req) as r:
                self.buf, self.buf_start = r.read(), self.pos
        o = self.pos - self.buf_start
        data = self.buf[o:o + (end - self.pos)]
        self.pos += len(data)
        return data

    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)


def zip_urls(year):
    html = urllib.request.urlopen(urllib.request.Request(MIRROR + year + "/", headers=UA)).read().decode("utf8", "replace")
    names = sorted(set(re.findall(r'href="([^"]+\.zip)"', html)))
    return [MIRROR + year + "/" + n for n in names]


def index():
    with open(INDEX, "w", newline="", encoding="utf8") as f:
        w = csv.writer(f, delimiter="\t")
        for y in YEARS:
            for url in zip_urls(y):
                try:
                    z = zipfile.ZipFile(HTTPRangeFile(url))
                except Exception as e:
                    print("skip", url, e); continue
                n = 0
                for info in z.infolist():
                    if info.filename.lower().endswith((".wav", ".flac", ".aif", ".aiff")):
                        w.writerow([y, url, info.filename, info.file_size]); n += 1
                print(y, urllib.parse.unquote(url.rsplit("/", 1)[1]), n, "files", flush=True)


def rows():
    with open(INDEX, encoding="utf8") as f:
        return list(csv.reader(f, delimiter="\t"))


def find(pat):
    rx = re.compile(pat, re.I)
    for y, url, m, size in rows():
        if rx.search(m):
            print(f"{y}\t{int(size) / 1e6:6.1f}MB\t{m}")


def get(members, OUT):
    os.makedirs(OUT, exist_ok=True)
    by_url = {}
    for y, url, m, size in rows():
        if m in members:
            by_url.setdefault(url, []).append((y, m))
    for url, items in by_url.items():
        z = zipfile.ZipFile(HTTPRangeFile(url))
        for y, m in items:
            dst = os.path.join(OUT, y, os.path.basename(m))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with z.open(m) as src, open(dst, "wb") as out:
                out.write(src.read())
            print("got", dst, flush=True)
    missing = set(members) - {m for v in by_url.values() for _, m in v}
    for m in missing:
        print("not in index:", m)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if not a or a[0] not in ("index", "find", "get") or (a[0] == "find" and len(a) < 2):
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == "index": index()
    elif cmd == "find": find(a[1])
    elif cmd == "get":
        rest = a[1:]
        if rest[:1] == ["--story"] and len(rest) > 1:
            dest, rest = os.path.join(rest[1], "media", "audio", "sfx", "src"), rest[2:]
        elif rest[:1] == ["--dest"] and len(rest) > 1:
            dest, rest = rest[1], rest[2:]
        else:
            sys.exit("get needs --story <story dir> or --dest <dir> before the member names")
        get(rest, dest)
