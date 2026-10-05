#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reply_core 离线单元测试：python3 tests/test_reply_core.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reply_core import (CooldownTracker, DEFAULT_IMAGE_DIR,  # noqa: E402
                        RecentMessages, appeared_above, match_keyword,
                        parse_rules, resolve_image)

FAILED = []


def check(name, cond):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}")
        FAILED.append(name)


print("[1] 规则解析：字符串写法")
rules, errors = parse_rules(["姆唔，姆唔，tu_1", "早安，早安哦", "晚安，，tu_2，120", "", "# 注释"])
check("解析出 3 条规则", len(rules) == 3)
check("无报错", errors == [])
check("触发词/回复/图片", (rules[0].keyword, rules[0].reply, rules[0].image) == ("姆唔", "姆唔", "tu_1"))
check("省略图片与冷却", (rules[1].image, rules[1].cooldown) == ("", None))
check("只发图 + 冷却 120", (rules[2].reply, rules[2].image, rules[2].cooldown) == ("", "tu_2", 120.0))

print("[2] 规则解析：JSON / 多行 / 异常")
rules, errors = parse_rules(json.dumps([
    {"keyword": "好耶", "reply": "好耶！", "match_type": "regex", "cooldown": 60},
    {"keyword": "", "reply": "x"},
    {"keyword": "(", "match_type": "regex"},
]))
check("跳过空 keyword", len(rules) == 1)
check("正则已编译", rules[0].pattern is not None)
check("冷却解析", rules[0].cooldown == 60.0)
check("报错信息有 2 条", len(errors) == 2)

rules, errors = parse_rules("姆唔，姆唔\ntu_1 测试，测试")
check("多行字符串解析", len(rules) == 2)
rules, errors = parse_rules("[")
check("坏 JSON 不崩", rules == [] and len(errors) == 1)
rules, errors = parse_rules(None)
check("None 安全", rules == [])

print("[3] 关键词匹配")
rules, _ = parse_rules(["姆唔，回复"])
r = rules[0]
check("包含匹配", match_keyword("你在说什么姆唔啦", r))
check("大小写无关", match_keyword("HELLO", parse_rules([{"keyword": "hello", "reply": "x"}])[0][0]))
check("不匹配", not match_keyword("无关内容", r))
exact = parse_rules([{"keyword": "早安", "reply": "x", "match_type": "exact"}])[0][0]
check("精确匹配命中", match_keyword("早安", exact))
check("精确匹配不中", not match_keyword("早上好早安", exact))
rx = parse_rules([{"keyword": "^好耶+$", "reply": "x", "match_type": "regex"}])[0][0]
check("正则匹配", match_keyword("好耶耶", rx) and not match_keyword("不耶", rx))

print("[4] 图片解析")
with tempfile.TemporaryDirectory() as d:
    png = os.path.join(d, "tu_1.png")
    open(png, "wb").close()
    check("图名自动补扩展名", resolve_image("tu_1", d) == ("file", os.path.abspath(png)))
    check("带扩展名", resolve_image("tu_1.png", d) == ("file", os.path.abspath(png)))
    check("绝对路径", resolve_image(png, d) == ("file", os.path.abspath(png)))
    check("网络链接", resolve_image("https://a.com/b.png", d) == ("url", "https://a.com/b.png"))
    check("找不到返回 None", resolve_image("not_exist", d) is None)
    check("空值安全", resolve_image("", d) is None)
check("默认目录常量", DEFAULT_IMAGE_DIR.endswith("/tu"))

print("[5] 冷却控制")
tracker = CooldownTracker()
check("首次允许", tracker.allow("k", 30, now=100))
tracker.touch("k", 30, now=100)
check("冷却中拒绝", not tracker.allow("k", 30, now=110))
check("剩余时间", abs(tracker.remaining("k", now=110) - 20) < 1e-6)
check("到期后允许", tracker.allow("k", 30, now=131))
check("冷却 0 不限制", tracker.allow("z", 0, now=0))
tracker.touch("z", 0, now=0)
check("冷却 0 不记录", tracker.remaining("z", now=0) == 0)
tracker.touch("k", 5, now=200)
tracker.cleanup(now=300)
check("cleanup 清空过期", tracker.remaining("k", now=300) == 0)

print("[6] 上面已有触发词去重")
recent = RecentMessages()
rule = parse_rules(["姆唔，姆唔"])[0][0]
check("空会话取不到", recent.above("g1", "u1") == [])
recent.remember("g1", "u1", "早上好", now=0)
check("取到上一条", recent.above("g1", "u1", now=1) == ["早上好"])
check("还没出现触发词", not appeared_above(recent.above("g1", "u1", now=1), rule))
recent.remember("g1", "u1", "姆唔", now=2)
check("上面已有触发词", appeared_above(recent.above("g1", "u1", now=3), rule))
recent.remember("g1", "u1", "哦", now=3)
check("只看紧邻一条就不算", appeared_above(recent.above("g1", "u1", window=1, now=4), rule) is False)
check("window=2 能查到", appeared_above(recent.above("g1", "u1", window=2, now=4), rule))
recent.remember("g1", "u2", "姆唔", now=4)
check("同人限定忽略别人", recent.above("g1", "u1", same_user_only=True, now=5) == ["哦"])
check("不限同人能看到别人的", recent.above("g1", "u1", same_user_only=False, now=5) == ["姆唔"])
check("默认不限同人", recent.above("g1", "u1", now=5) == ["姆唔"])
check("会话之间互相隔离", recent.above("g2", "u1", now=5) == [])
check("超出时间范围取不到", recent.above("g1", "u1", seconds=0.5, now=100) == [])
recent.forget("g1")
check("清空单个会话", recent.above("g1", "u1", now=6) == [])
recent.remember("g2", "u1", "在吗", now=6)
recent.forget()
check("清空全部会话", recent.above("g2", "u1", now=7) == [])

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：" + ", ".join(FAILED))
    sys.exit(1)
print("全部通过")
