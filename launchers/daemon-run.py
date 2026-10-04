#!/usr/bin/env python3
"""daemon-run.py — 把一条命令彻底脱钩地跑起来（macOS 没有 setsid 的替代）。

普通 `nohup cmd &` 仍然属于当前**会话/进程组**，终端或父 agent 收尾时会连带被回收。
本脚本 double-fork + setsid，让子进程进入新会话，父进程立即返回 → 真正常驻。

用法:
  /usr/bin/python3 daemon-run.py --log /path/out.log -- /usr/bin/python3 app.py --port 8790
"""
import argparse
import os
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, help="stdout/stderr 追加到这个文件")
    ap.add_argument("--env", action="append", default=[], help="额外环境变量 K=V，可重复")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- 之后的命令")
    a = ap.parse_args()

    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        print("用法: daemon-run.py --log <file> -- <cmd...>", file=sys.stderr)
        return 2

    env = dict(os.environ)
    for kv in a.env:
        k, _, v = kv.partition("=")
        env[k] = v

    os.makedirs(os.path.dirname(os.path.abspath(a.log)), exist_ok=True)

    pid = os.fork()
    if pid > 0:                                   # 父：立刻返回
        print(f"daemon pid={pid} log={a.log}")
        return 0

    os.setsid()                                   # 子：脱离原会话/进程组
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)                               # 中间进程退出，孙进程被 init 收养

    with open(os.devnull, "rb") as devnull, open(a.log, "ab") as log:
        os.dup2(devnull.fileno(), 0)
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
    try:
        os.chdir(os.path.expanduser("~"))
    except Exception:
        pass
    os.execvpe(cmd[0], cmd, env)                  # 永驻进程
    os._exit(127)


if __name__ == "__main__":
    sys.exit(main())
