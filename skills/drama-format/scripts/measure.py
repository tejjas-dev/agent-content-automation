#!/usr/bin/env python3
"""Caption helpers the model cannot do reliably by eye.

  measure.py FILE...        -> UTF-16 units per file (Telegram counts emoji as 2); keep <= 950
  measure.py plan N [MAX]   -> balanced post sizes for N links, MAX per post (default 12): 13 -> 7 6
"""
import sys


def units(text):
    return len(text.encode("utf-16-le")) // 2


def plan(n, mx=12):
    k = -(-n // mx)
    q, r = divmod(n, k)
    return [q + 1] * r + [q] * (k - r)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["plan"] and len(a) >= 2:
        print(" ".join(map(str, plan(int(a[1]), int(a[2]) if len(a) > 2 else 12))))
    elif a:
        for f in a:
            print(f"{units(open(f, encoding='utf-8').read())} {f}")
    else:
        print(__doc__)
