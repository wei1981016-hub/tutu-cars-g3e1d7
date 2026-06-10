#!/usr/bin/env python3
"""
图图认车车 - 一键生成定制版礼物（孩子名字 + 家长克隆声音 + 独立网址）

流程：让小朋友的爸爸/妈妈录一段 20 秒左右的清晰语音（m4a/mp3/wav 都行），然后：

  export DASHSCOPE_API_KEY=sk-xxx
  python3 make_gift.py 乐乐 --sample ~/Downloads/乐乐妈妈.m4a
  python3 make_gift.py 朵朵 --sample 朵朵爸爸.mp3 --en Duoduo
  python3 make_gift.py 乐乐 --voice cosyvoice-v2-xxx     # 已有克隆音色ID时直接用
  加 --no-deploy 只生成本地文件不发布

步骤：克隆家长音色（录音经主仓库的 GitHub Pages 临时中转给阿里云——release 和
  raw 地址阿里云拉不到，github.io 实测可以；注册完立即 force-push 抹掉，不留历史）
  → 用该音色生成全部 153 条语音 → 替换游戏里的宝宝名字 → 发布成独立网址。
同一音色的 150 条通用语音会缓存在 gifts/_packs/，同一家重新生成时秒出。

建议给家长的录音稿（自然、有感情地念）：
  「宝宝你好呀！今天我们一起来认识好多车车，有挖掘机，有消防车，
    还有大吊车！它们每一个都有自己的本领哦，准备好了吗？出发咯！」
"""
import os
import re
import sys
import time
import shutil
import string
import random
import tempfile
import argparse
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
GIFTS = os.path.join(ROOT, "gifts")
ENROLL_MODEL = "cosyvoice-v2"   # API 声音复刻的目标模型（合成时模型须一致）
sys.path.insert(0, ROOT)
from generate_audio import NAME_KEYS  # noqa: E402


def run(cmd, cwd=None, check=True):
    print("  $", " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True, capture_output=True, cwd=cwd)


def rand_slug(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def main_repo():
    r = run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=ROOT)
    return r.stdout.strip()


def enroll_voice(sample, slug):
    """用家长录音克隆音色：主仓库 Pages 临时中转 -> 复刻 -> force-push 抹掉，返回音色ID"""
    if not os.path.isfile(sample):
        sys.exit("录音文件不存在：%s" % sample)
    ext = (os.path.splitext(sample)[1] or ".mp3").lower()
    if ext not in (".mp3", ".wav", ".m4a", ".aac"):
        sys.exit("录音格式请用 mp3/wav/m4a/aac，收到：%s" % ext)
    dirty = run(["git", "status", "--porcelain", "-uno"], cwd=ROOT).stdout.strip()
    if dirty:
        sys.exit("主仓库有未提交的改动（录音中转需要临时提交+force-push 回退）：\n%s\n"
                 "请先 git commit 或还原这些改动再生成礼物" % dirty)
    repo = main_repo()
    owner, rname = repo.split("/")
    head = run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    fname = "voice-%s%s" % (slug, ext)
    tmp_dir = os.path.join(ROOT, "tmpvoice")
    os.makedirs(tmp_dir, exist_ok=True)
    shutil.copy2(sample, os.path.join(tmp_dir, fname))
    url = "https://%s.github.io/%s/tmpvoice/%s" % (owner, rname, fname)
    print("克隆家长音色（录音经 %s 临时中转，注册后立即抹掉）" % url)
    vid = None
    try:
        run(["git", "add", "tmpvoice/" + fname], cwd=ROOT)
        run(["git", "commit", "-q", "-m", "tmp voice sample (auto-removed)"], cwd=ROOT)
        run(["git", "push", "-q"], cwd=ROOT)
        print("等待 Pages 发布录音", end="", flush=True)
        for _ in range(36):
            code = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                                  capture_output=True, text=True).stdout
            if code == "200":
                print(" OK")
                break
            print(".", end="", flush=True)
            time.sleep(10)
        else:
            sys.exit("\n录音中转地址一直没就绪，稍后重试")
        import dashscope
        from dashscope.audio.tts_v2 import VoiceEnrollmentService
        dashscope.api_key = os.environ["DASHSCOPE_API_KEY"]
        svc = VoiceEnrollmentService()
        prefix = re.sub(r"[^a-z0-9]", "", slug.lower())[:9] or "kid"
        for attempt in range(3):
            try:
                vid = svc.create_voice(target_model=ENROLL_MODEL, prefix=prefix, url=url)
                break
            except Exception as e:
                print("  复刻失败（第%d次）：%s" % (attempt + 1, e))
                time.sleep(3)
    finally:
        # 无论成败都把临时提交从历史里抹掉
        run(["git", "reset", "--hard", head, "-q"], cwd=ROOT, check=False)
        run(["git", "push", "--force", "-q"], cwd=ROOT, check=False)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    if not vid:
        sys.exit("声音复刻失败。备选：到阿里云百炼控制台手动复刻，拿到音色ID后用 --voice 传入")
    print("音色克隆成功：%s（记下来，这家以后重新生成可直接 --voice 复用）" % vid)
    time.sleep(5)  # 新音色就绪需要几秒
    return vid


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
    """音色包缓存：同一音色的通用语音复用，仅含名字的 3 条必须重新生成"""
    pack = os.path.join(GIFTS, "_packs", re.sub(r"[^A-Za-z0-9._-]", "_", voice))
    os.makedirs(dst_audio, exist_ok=True)
    pack_ready = os.path.isdir(pack) and len(os.listdir(pack)) > 0
    if pack_ready:
        print("命中音色包缓存（%d 个文件），只需生成 %d 条含名字的语音" %
              (len(os.listdir(pack)), len(NAME_KEYS)))
        for f in os.listdir(pack):
            shutil.copy2(os.path.join(pack, f), os.path.join(dst_audio, f))
    for k in NAME_KEYS:
        p = os.path.join(dst_audio, k + ".mp3")
        if os.path.exists(p):
            os.remove(p)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "generate_audio.py"),
                        "--name", name, "--voice", voice, "--outdir", dst_audio])
    if r.returncode != 0:
        sys.exit("语音生成失败")
    missing = [k for k in NAME_KEYS if not os.path.exists(os.path.join(dst_audio, k + ".mp3"))]
    if missing:
        sys.exit("语音生成不完整，缺：%s（重跑一次即可补齐）" % missing)
    if not pack_ready:
        os.makedirs(pack, exist_ok=True)
        for f in os.listdir(dst_audio):
            if f.replace(".mp3", "") not in NAME_KEYS:
                shutil.copy2(os.path.join(dst_audio, f), os.path.join(pack, f))
        print("音色包已缓存到 %s" % os.path.relpath(pack, ROOT))


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
    ap = argparse.ArgumentParser(description="生成定制版认车车礼物")
    ap.add_argument("name", help="宝宝名字（中文，如 乐乐）")
    ap.add_argument("--sample", default="", help="家长录音文件（m4a/mp3/wav，约20秒），自动克隆音色")
    ap.add_argument("--voice", default="", help="已有的克隆音色ID（与 --sample 二选一）")
    ap.add_argument("--en", default="", help="英文名/拼音昵称（副标题用，可不填）")
    ap.add_argument("--slug", default="", help="网址后缀，默认随机")
    ap.add_argument("--no-deploy", action="store_true", help="只生成本地文件不发布")
    ap.add_argument("--enroll-only", action="store_true", help="只克隆音色拿ID，不生成游戏")
    args = ap.parse_args()

    if not os.environ.get("DASHSCOPE_API_KEY"):
        sys.exit("缺少环境变量 DASHSCOPE_API_KEY")
    if not args.sample and not args.voice:
        sys.exit("礼物的灵魂是家长的声音：请用 --sample 提供家长录音（自动克隆），"
                 "或用 --voice 提供已克隆的音色ID")

    slug = args.slug or rand_slug()
    voice = args.voice or enroll_voice(args.sample, slug)
    if args.enroll_only:
        print("\n音色ID：%s\n之后用：python3 make_gift.py %s --voice %s" % (voice, args.name, voice))
        return

    gift_dir = os.path.join(GIFTS, "%s-%s" % (args.name, slug))
    os.makedirs(gift_dir, exist_ok=True)
    print("== 为「%s」生成定制版 -> %s" % (args.name, os.path.relpath(gift_dir, ROOT)))

    build_html(args.name, args.en, gift_dir)
    build_audio(args.name, voice, os.path.join(gift_dir, "audio"))

    if args.no_deploy:
        print("\n完成（未发布）。本地预览：cd '%s' && python3 -m http.server 18999" % gift_dir)
        print("音色ID：%s" % voice)
        return
    url = deploy(gift_dir, slug)
    print("\n🎁 「%s认车车」已上线：%s" % (args.name, url))
    print("音色ID：%s（这家以后更新可复用）" % voice)
    print("发给家长：iPad Safari 打开 -> 分享 -> 添加到主屏幕")


if __name__ == "__main__":
    main()
