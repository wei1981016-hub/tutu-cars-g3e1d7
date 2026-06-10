#!/usr/bin/env python3
"""
图图认车车 - 批量生成语音文件（阿里云 DashScope CosyVoice）

用法：
  export DASHSCOPE_API_KEY=sk-xxx          # 不要写进代码/文件里
  pip install dashscope
  python3 generate_audio.py                # 默认音色 longxiaochun_v2（女声，中英双语）
  python3 generate_audio.py --voice longwan_v2        # 换内置音色
  python3 generate_audio.py --voice cosyvoice-xxx-id  # 用克隆出来的音色ID
  python3 generate_audio.py --list         # 只列出所有台词，不生成
  python3 generate_audio.py --force        # 已存在的文件也重新生成

生成结果放到 ./audio/<key>.mp3，游戏会自动加载；缺文件时自动回退系统TTS。
台词文本与 index.html 中保持一致，改了 index.html 的文案记得同步这里。
"""
import os
import sys
import time
import argparse

# ============ 台词表（key -> (文本, 语言)） ============
VEHICLES = [
    # (id, 中文名, 英文名, 用途, 互动语)
    ("excavator", "挖掘机", "Excavator", "挖掘机有长长的手臂和大铲斗，最会挖土啦！", "挖呀挖，挖到一大铲土！"),
    ("bulldozer", "推土机", "Bulldozer", "推土机有大大的铲刀，可以把土推得平平的！", "推呀推，把土推平啦！"),
    ("loader", "装载机", "Loader", "装载机用大铲子把沙土铲起来，装到卡车上！", "铲起来，装上车咯！"),
    ("crane", "吊车", "Crane", "吊车的长胳膊可以把重重的东西吊到高高的地方！", "吊钩降下来，把重物吊起来咯！"),
    ("towercrane", "塔吊", "Tower Crane", "塔吊站得高高的，帮忙盖大楼，吊起好多材料！", "小车跑一跑，把材料吊上楼顶！"),
    ("dumptruck", "翻斗车", "Dump Truck", "翻斗车的车斗会翘起来，哗啦，把土倒出来啦！", "车斗翘起来，哗啦，土倒出来啦！"),
    ("mixer", "搅拌车", "Concrete Mixer", "搅拌车的大罐子会转呀转，把水泥搅拌得均匀！", "大罐子转呀转，水泥拌好啦！"),
    ("roller", "压路机", "Road Roller", "压路机有大大的铁滚筒，把马路压得平平整整！", "滚筒轰隆隆，马路压平啦！"),
    ("forklift", "叉车", "Forklift", "叉车有两个铁叉子，可以叉起重重的货物！", "叉子升起来，货物搬好啦！"),
    ("pumptruck", "泵车", "Pump Truck", "泵车有长长的管子手臂，把水泥送到高高的楼上！", "长臂伸出去，水泥送上楼咯！"),
    ("grader", "平地机", "Grader", "平地机肚子下面有一把长刀，把地刮得平平的！", "长刀刮一刮，地面平平的！"),
    ("miningtruck", "矿用大卡车", "Mining Truck", "矿用大卡车是超级大力士，轮子比爸爸还高，能拉好多好多矿石！", "大力士出发，矿石运走啦！"),
    ("firetruck", "消防车", "Fire Truck", "着火了别怕！消防车呜哇呜哇赶来灭火！", "云梯升起来，呜哇呜哇去灭火！"),
    ("policecar", "警车", "Police Car", "警车闪着蓝红灯，保护大家的安全！", "警灯闪闪，呜哇呜哇出发啦！"),
    ("ambulance", "救护车", "Ambulance", "有人生病了，救护车快快送他去医院！", "救护车呜哇呜哇，快快去医院！"),
    ("bus", "公交车", "Bus", "公交车好长呀，能带好多人一起出门！", "车门打开啦，请上车！"),
    ("garbagetruck", "垃圾车", "Garbage Truck", "垃圾车把垃圾吃进肚子，让街道干干净净！", "盖子打开，垃圾吃进肚子里！"),
    ("watertruck", "洒水车", "Water Truck", "洒水车一边唱歌一边洒水，给马路洗澡澡！", "哗啦啦，洒水车给马路洗澡澡！"),
    ("schoolbus", "校车", "School Bus", "黄色的校车，接小朋友们上学去！", "停车牌伸出来，小朋友们上车啦！"),
    ("tractor", "拖拉机", "Tractor", "拖拉机突突突，在田地里帮农民伯伯干活！", "突突突突，拖拉机干活啦！"),
]
SCENES = [
    ("thief", "不好啦！马路上有个坏人在捣乱！快，开哪辆车去抓住他？", "呜哇呜哇！警察叔叔把坏人抓住啦！图图立大功！"),
    ("fire", "着火啦！小房子着火啦！快开哪辆车去灭火？", "水枪喷水，火扑灭啦！消防员真勇敢！"),
    ("sick", "哎呀，有人生病了，好难受呀！快开哪辆车去帮忙？", "呜哇呜哇，快快送到医院，病人得救啦！"),
    ("pit", "工地上要挖一个大大的坑，开哪辆车来帮忙呀？", "挖呀挖，大坑挖好啦！真能干！"),
    ("dirtpile", "这里有一大堆土，要把它运走，开哪辆车呢？", "装得满满的，土运走啦！"),
    ("bumpy", "新修的马路坑坑洼洼的，开哪辆车把它压平呀？", "轰隆隆压过去，马路变得平平的！"),
    ("dusty", "马路上好多灰尘，脏脏的，开哪辆车来帮忙？", "哗啦啦洒洒水，马路干干净净！"),
    ("trash", "垃圾桶满出来啦，臭臭的，开哪辆车来收垃圾？", "垃圾都吃进肚子，街道变干净啦！"),
    ("school", "叮铃铃，要上学啦，小朋友们在等哪辆车呀？", "小朋友们都上车啦，出发去学校咯！"),
    ("box", "仓库里的大箱子好重呀，开哪辆车把它搬起来？", "叉子一抬，大箱子搬好啦！"),
    ("beam", "盖大楼要把钢梁吊到楼顶，开哪辆车来帮忙？", "钢梁吊上去啦，大楼越盖越高！"),
    ("farm", "田地里要翻土种庄稼，农民伯伯在等谁呀？", "突突突，田地翻好啦，等着大丰收！"),
]
PRAISE = ["太棒了！", "真厉害！", "答对啦！", "图图真棒！", "好聪明呀！"]


def build_lines():
    lines = {}
    for vid, zh, en, desc, act in VEHICLES:
        lines["n_" + vid] = (zh, "zh")
        lines["e_" + vid] = (en, "en")
        lines["d_" + vid] = (desc, "zh")
        lines["a_" + vid] = (act, "zh")
        lines["q_" + vid] = ("找一找，哪一个是" + zh + "？", "zh")
        lines["w_" + vid] = ("这是" + zh + "，", "zh")
    for sid, q, win in SCENES:
        lines["s_" + sid] = (q, "zh")
        lines["sw_" + sid] = (win, "zh")
    for i, p in enumerate(PRAISE):
        lines["praise_%d" % i] = (p, "zh")
    lines["welcome"] = ("你好呀！欢迎来到图图认车车！点一点，认识好多车车吧！", "zh")
    lines["try_again"] = ("哎呀，再试试！", "zh")
    lines["play_hint"] = ("用小手把车车拖到上面的画里，试试看！", "zh")
    lines["play_wrong"] = ("再想想，应该开哪辆车呢？", "zh")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="longxiaochun_v2", help="CosyVoice 音色名或克隆音色ID")
    ap.add_argument("--model", default="cosyvoice-v2", help="模型名")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio"))
    ap.add_argument("--list", action="store_true", help="只列出台词，不生成")
    ap.add_argument("--force", action="store_true", help="覆盖已有文件")
    args = ap.parse_args()

    lines = build_lines()
    if args.list:
        for k, (t, lang) in lines.items():
            print("%-16s [%s] %s" % (k, lang, t))
        print("\n共 %d 条" % len(lines))
        return

    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        sys.exit("缺少环境变量 DASHSCOPE_API_KEY（不要把 key 写进代码）")
    try:
        import dashscope
        from dashscope.audio.tts_v2 import SpeechSynthesizer
    except ImportError:
        sys.exit("请先安装：pip install dashscope")
    dashscope.api_key = key

    # 克隆音色ID形如 cosyvoice-v3.5-plus-bailian-xxx，模型必须与克隆时的目标模型一致
    if args.voice.startswith("cosyvoice-v") and "-bailian-" in args.voice:
        target = args.voice.split("-bailian-")[0]
        if args.model != target:
            print("检测到克隆音色，模型自动切换为 %s" % target)
            args.model = target

    try:
        from dashscope.audio.tts_v2 import AudioFormat
        fmt = AudioFormat.MP3_22050HZ_MONO_256KBPS
    except Exception:
        fmt = None

    os.makedirs(args.outdir, exist_ok=True)
    todo = [(k, t) for k, (t, _lang) in lines.items()
            if args.force or not os.path.exists(os.path.join(args.outdir, k + ".mp3"))]
    print("音色=%s 模型=%s，共 %d 条，需生成 %d 条" % (args.voice, args.model, len(lines), len(todo)))

    fail = []
    for i, (k, text) in enumerate(todo, 1):
        path = os.path.join(args.outdir, k + ".mp3")
        audio, err = None, None
        for attempt in range(3):
            try:
                kw = {"model": args.model, "voice": args.voice, "speech_rate": 0.9}
                if fmt is not None:
                    kw["format"] = fmt
                syn = SpeechSynthesizer(**kw)
                audio = syn.call(text)
                if not audio:
                    raise RuntimeError("空返回")
                break
            except Exception as e:
                audio, err = None, e
                time.sleep(1.5 * (attempt + 1))
        if audio:
            with open(path, "wb") as f:
                f.write(audio)
            print("[%d/%d] %s OK (%d bytes)" % (i, len(todo), k, len(audio)))
        else:
            fail.append(k)
            print("[%d/%d] %s 失败: %s" % (i, len(todo), k, err))
        time.sleep(0.3)  # 温和限速

    if fail:
        print("\n失败 %d 条：%s\n重跑本脚本会自动补齐缺的文件。" % (len(fail), " ".join(fail)))
    else:
        print("\n全部完成 ✅ 音频在 %s" % args.outdir)


if __name__ == "__main__":
    main()
