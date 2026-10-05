#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关键词自动回复（Keyword Reply）—— AstrBot 插件

监测到指定内容，就发送指定内容，可附带一张图片，并带冷却防刷屏。

配置里的规则写法（每条一行）::

    触发词，回复内容，图片，冷却秒数

例如::

    姆唔，姆唔，tu_1          # 监测到「姆唔」→ 回复「姆唔」并附图片 tu_1
    早安，早安哦             # 只发文字
    晚安，，tu_2，120        # 只发图，冷却 120 秒

图片只写图名即可，默认去 ``/root/AstrBot/data/workspaces/tu`` 里找，
自动补扩展名（tu_1 → tu_1.png）；也支持绝对路径和 http(s) 链接。
"""
import os

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star

try:  # 兼容包 / 非包两种加载方式
    from .reply_core import (DEFAULT_IMAGE_DIR, CooldownTracker, RecentMessages,
                             appeared_above, match_keyword, parse_rules,
                             resolve_image)
except ImportError:  # pragma: no cover
    from reply_core import (DEFAULT_IMAGE_DIR, CooldownTracker, RecentMessages,
                            appeared_above, match_keyword, parse_rules,
                            resolve_image)

VALID_SCOPES = ("group", "user", "global")


class KeywordReplyPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self.cooldown = CooldownTracker()
        self.recent = RecentMessages()
        self.rules = []
        self._rules_sig = None
        self._load_rules()

    # ---------------- 配置读取 ----------------
    def _load_rules(self) -> None:
        raw = self.config.get("rules", []) or []
        self._rules_sig = repr(raw)
        rules, errors = parse_rules(raw, self._default_match_type())
        self.rules = rules
        for err in errors:
            logger.warning(f"[KeywordReply] {err}")
        logger.info(f"[KeywordReply] 已加载 {len(self.rules)} 条关键词规则")

    def _default_match_type(self) -> str:
        mt = str(self.config.get("match_type", "contains") or "contains").strip()
        return mt if mt in ("contains", "exact", "regex") else "contains"

    def _default_cooldown(self) -> float:
        try:
            return max(0.0, float(self.config.get("cooldown_seconds", 30) or 0))
        except (TypeError, ValueError):
            return 30.0

    def _cooldown_scope(self) -> str:
        scope = str(self.config.get("cooldown_scope", "group") or "group").strip()
        return scope if scope in VALID_SCOPES else "group"

    def _image_dir(self) -> str:
        return str(self.config.get("image_dir") or DEFAULT_IMAGE_DIR).strip() or DEFAULT_IMAGE_DIR

    def _bool(self, key: str, default: bool = True) -> bool:
        val = self.config.get(key, default)
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on", "是")
        return bool(val)

    def _no_quote(self) -> bool:
        """是否绕过框架的引用回复装饰（只影响本插件的消息）。"""
        return self._bool("no_quote", True)

    # -------- 「上面已有触发词就不发」的配置 --------
    def _dedup_enabled(self) -> bool:
        return self._bool("dedup_enabled", True)

    def _dedup_window(self) -> int:
        try:
            return max(1, int(self.config.get("dedup_window", 1) or 1))
        except (TypeError, ValueError):
            return 1

    def _dedup_seconds(self) -> float:
        try:
            return max(0.0, float(self.config.get("dedup_seconds", 0) or 0))
        except (TypeError, ValueError):
            return 0.0

    def _dedup_same_user_only(self) -> bool:
        """默认 False：群里别人上面说过同样的触发词，也算「上面已有」。"""
        return self._bool("dedup_same_user_only", False)

    def _session_key(self, event, group_id: str, sender_id: str) -> str:
        """会话标识：群聊按群、私聊按人；优先用框架给的 umo。"""
        return str(getattr(event, "unified_msg_origin", "") or group_id or sender_id)

    def _above_texts(self, session_key: str, sender_id: str) -> list:
        """取「上面」的消息文本，用于判断触发词是不是刚出现过。"""
        if not self._dedup_enabled():
            return []
        return self.recent.above(
            session_key,
            sender_id,
            window=self._dedup_window(),
            seconds=self._dedup_seconds(),
            same_user_only=self._dedup_same_user_only(),
        )

    def _id_list(self, key: str) -> set[str]:
        raw = self.config.get(key, []) or []
        if isinstance(raw, str):
            raw = raw.replace("，", ",").split(",")
        return {str(x).strip() for x in raw if str(x).strip()}

    def _ensure_rules(self) -> None:
        """配置在 WebUI 改动后，无需重载插件也能生效。"""
        if repr(self.config.get("rules", []) or []) != self._rules_sig:
            self._load_rules()

    def _cooldown_key(self, index: int, rule, group_id: str, sender_id: str) -> str:
        scope = self._cooldown_scope()
        if scope == "user":
            tail = sender_id
        elif scope == "global":
            tail = "global"
        else:
            tail = group_id or sender_id
        return f"{scope}:{index}:{rule.keyword}:{tail}"

    # ---------------- 消息监听 ----------------
    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        try:
            self._ensure_rules()
            text = (event.get_message_str() or "").strip()
            if not text:
                return
            sender_id = str(event.get_sender_id() or "")
            self_id = str(event.get_self_id() or "")
            group_id = str(event.get_group_id() or "")
            is_group = bool(group_id)

            if is_group and not self._bool("enable_group", True):
                return
            if not is_group and not self._bool("enable_private", True):
                return

            # 机器人自己 / 黑名单用户 / 黑名单群不触发
            if self._bool("ignore_bot", True) and sender_id and sender_id == self_id:
                return
            if sender_id in self._id_list("ignore_user_ids"):
                return
            if is_group and group_id in self._id_list("ignore_group_ids"):
                return

            # 「上面」的消息先取出来（不含本条），再把本条记进去
            session_key = self._session_key(event, group_id, sender_id)
            above = self._above_texts(session_key, sender_id)
            self.recent.remember(session_key, sender_id, text)

            for index, rule in enumerate(self.rules):
                if not rule.has_content or not match_keyword(text, rule):
                    continue

                # 上面已经出现过同一个触发词，就不再重复回复
                if appeared_above(above, rule):
                    logger.debug(
                        f"[KeywordReply] 规则「{rule.keyword}」上面已出现过，跳过"
                    )
                    continue

                cd = rule.cooldown if rule.cooldown is not None else self._default_cooldown()
                key = self._cooldown_key(index, rule, group_id, sender_id)
                if not self.cooldown.allow(key, cd):
                    logger.debug(
                        f"[KeywordReply] 规则「{rule.keyword}」冷却中，"
                        f"剩余 {self.cooldown.remaining(key):.1f}s"
                    )
                    hint = str(self.config.get("cooldown_hint", "") or "").strip()
                    if hint and self.cooldown.allow(key + ":hint", cd):
                        self.cooldown.touch(key + ":hint", cd)
                        if self._no_quote():
                            await event.send(MessageChain(chain=[Plain(hint)]))
                        else:
                            yield event.plain_result(hint)
                    return

                chain = []
                if rule.reply:
                    chain.append(Plain(rule.reply))

                if rule.image:
                    resolved = resolve_image(rule.image, self._image_dir())
                    if resolved is None:
                        logger.warning(
                            f"[KeywordReply] 规则「{rule.keyword}」的图片找不到：{rule.image}"
                        )
                    elif resolved[0] == "url":
                        chain.append(Image.fromURL(resolved[1]))
                    else:
                        chain.append(Image.fromFileSystem(resolved[1]))

                if not chain:
                    return

                self.cooldown.touch(key, cd)
                self.cooldown.cleanup()
                logger.info(f"[KeywordReply] 命中规则「{rule.keyword}」→ 已发送")
                if self._no_quote():
                    # 直接发送，绕过框架 result_decorate 的「引用原消息」装饰
                    await event.send(MessageChain(chain=chain))
                else:
                    yield event.chain_result(chain)
                return  # 一条消息只触发第一条命中的规则
        except Exception as e:
            logger.error(f"[KeywordReply] 处理消息异常: {e}")
