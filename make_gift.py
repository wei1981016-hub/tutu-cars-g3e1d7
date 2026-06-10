#!/usr/bin/env python3
"""
图图认车车 - 一键生成定制版礼物（换名字+语音，部署成独立网址）

用法：
  export DASHSCOPE_API_KEY=sk-xxx
  python3 make_gift.py 乐乐                          # 默认音色 longxiaochun_v2
  python3 make_gift.py 朵朵 --en Duoduo              # 副标题带英文名
  python3 make_gift.py 小明 --voice cosyvoice-xxx    # 用某家长的克隆音色
  python3 make_gift.py 乐乐 --no-deploy              # 只生成本地文件，不发布

原理：
  名字只出现在 3 条语音里（welcome / praise_3 / sw_thief）。同一音色的其余
  150 条缓存在 gifts/_packs/<音色>/ 复用——同音色第二个小朋友只需新生成 3 条。

产出：
  gifts/<名字>-<随机>/   本地成品（index.html + audio/）
  部署后输出 https://<你的GitHub用户名>.github.io/cars-<随机>/ 网址
"""
import os
import re
import sys
import time
import shutil
import string
import random
import argparse
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
GIFTS = os.path.join(ROOT, "gifts")
sys.path.insert(0, ROOT)
from generate_audio import NAME_KEYS  # noqa: E402


def run(cmd, **kw):
    print("  $", " ".join(cmd))
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def rand_slug(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def build_html(name, en, dst):
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    for pat, rep in [
        (r"const KID_NAME = '[^']*';", "const KID_NAME = '%s';" % name),
        (r"const KID_EN = '[^']*';", "const KID_EN = '%s';" % en),
    ]:
        src, n_sub = re.subn(pat, rep, src, count=1)
        if n_sub != 1:
            sys.exit("index.html 里没找到要替换的配置行：%s" % pat)
    open(os.path.join(dst, "index.html"), "w", encoding="utf-8").write(src)


def build_audio(name, voice, dst_audio):
    """音色包缓存复用：150 条共用，3 条含名字的单独生成。"""
    pack = os.path.join(GIFTS, "_packs", re.sub(r"[^A-Za-z0-9._-]", "_", voice))
    os.makedirs(dst_audio, exist_ok=True)
    pack_ready = os.path.isdir(pack) and len(os.listdir(pack)) > 0
    if pack_ready:
        print("命中音色包缓存（%d 个文件），只需生成 %d 条含名字的语音" %
              (len(os.listdir(pack)), len(NAME_KEYS)))
        for f in os.listdir(pack):
            shutil.copy2(os.path.join(pack, f), os.path.join(dst_audio, f))
    for k in NAME_KEYS:  # 名字相关的必须重新生成
        p = os.path.join(dst_audio, k + ".mp3")
        if os.path.exists(p):
            os.remove(p)
    run([sys.executable, os.path.join(ROOT, "generate_audio.py"),
         "--name", name, "--voice", voice, "--outdir", dst_audio])
    missing = [k for k in NAME_KEYS if not os.path.exists(os.path.join(dst_audio, k + ".mp3"))]
    if missing:
        sys.exit("语音生成不完整，缺：%s（重跑一次即可补齐）" % missing)
    if not pack_ready:  # 第一次用这个音色：把不含名字的存入缓存
        os.makedirs(pack, exist_ok=True)
        for f in os.listdir(dst_audio):
            if f.replace(".mp3", "") not in NAME_KEYS:
                shutil.copy2(os.path.join(dst_audio, f), os.path.join(pack, f))
        print("音色包已缓存到 %s（下次同音色秒出）" % os.path.relpath(pack, ROOT))


def deploy(gift_dir, slug):
    owner = run(["gh", "api", "user", "--jq", ".login"]).stdout.strip()
    repo = "cars-" + slug
    print("发布到 GitHub Pages：%s/%s" % (owner, repo))
    run(["git", "init", "-b", "main", "-q"], cwd=gift_dir)
    run(["git", "add", "-A"], cwd=gift_dir)
    run(["git", "commit", "-q", "-m", "customized cars game"], cwd=gift_dir)
    run(["gh", "repo", "create", repo, "--public", "--source", ".", "--push"], cwd=gift_dir)
    run(["gh", "api", "-X", "POST", "repos/%s/%s/pages" % (owner, repo),
         "-f", "source[branch]=main", "-f", "source[path]=/"])
    url = "https://%s.github.io/%s/" % (owner, repo)
    print("等待 Pages 构建", end="", flush=True)
    for _ in range(60):
        code = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                              capture_output=True, text=True).stdout
        if code == "200":
            print(" OK")
            return url
        print(".", end="", flush=True)
        time.sleep(10)
    print("\n构建还没好，稍后自己打开试试：%s" % url)
    return url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="宝宝名字（中文，如 乐乐）")
    ap.add_argument("--en", default="", help="英文名/拼音昵称（副标题用，可不填）")
    ap.add_argument("--voice", default="longxiaochun_v2",
                    help="CosyVoice 音色，或某家长的克隆音色ID")
    ap.add_argument("--slug", default="", help="网址后缀，默认随机")
    ap.add_argument("--no-deploy", action="store_true", help="只生成本地文件不发布")
    args = ap.parse_args()

    if not os.environ.get("DASHSCOPE_API_KEY"):
        sys.exit("缺少环境变量 DASHSCOPE_API_KEY")

    slug = args.slug or rand_slug()
    gift_dir = os.path.join(GIFTS, "%s-%s" % (args.name, slug))
    os.makedirs(gift_dir, exist_ok=True)
    print("== 为「%s」生成定制版 -> %s" % (args.name, os.path.relpath(gift_dir, ROOT)))

    build_html(args.name, args.en, gift_dir)
    build_audio(args.name, args.voice, os.path.join(gift_dir, "audio"))

    if args.no_deploy:
        print("\n完成（未发布）。本地预览：cd '%s' && python3 -m http.server 18999" % gift_dir)
        return
    url = deploy(gift_dir, slug)
    print("\n🎁 「%s认车车」已上线：%s" % (args.name, url))
    print("发给家长：iPad Safari 打开 -> 分享 -> 添加到主屏幕")


if __name__ == "__main__":
    main()
