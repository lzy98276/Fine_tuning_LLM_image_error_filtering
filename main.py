from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Image, Record, Video, File as FileComponent, At, Poke, Plain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("image_message_filter", "黎泽懿", "过滤图片消息的插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._wake_prefixes = ["/"]
        self._friend_needs_prefix = False

    def _is_media_message(self, event: AstrMessageEvent) -> bool:
        chain = event.get_messages()
        return any(isinstance(seg, (Image, Record, Video, FileComponent)) for seg in chain)

    def _normalize_wake_prefixes(self, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, (list, tuple, set)):
            prefixes = []
            for item in value:
                if isinstance(item, str) and item:
                    prefixes.append(item)
            return prefixes
        return []

    def _extract_wake_prefixes_from_mapping(self, mapping):
        if not isinstance(mapping, dict):
            return []
        prefixes = []
        prefixes.extend(self._normalize_wake_prefixes(mapping.get("wake_prefix")))
        provider_settings = mapping.get("provider_settings")
        if isinstance(provider_settings, dict):
            prefixes.extend(self._normalize_wake_prefixes(provider_settings.get("wake_prefix")))
        return prefixes

    def _load_wake_prefixes_from_context(self):
        ctx = getattr(self, "context", None)
        if ctx is None:
            return []

        candidates = []
        for attr in ("config", "cfg", "settings", "bot_config", "config_dict"):
            try:
                val = getattr(ctx, attr)
            except Exception:
                continue
            if isinstance(val, dict):
                candidates.append(val)

        for method_name in ("get_config", "get_config_dict", "get_cmd_config", "get_settings"):
            fn = getattr(ctx, method_name, None)
            if not callable(fn):
                continue
            try:
                val = fn()
            except Exception:
                continue
            if isinstance(val, dict):
                candidates.append(val)

        prefixes = []
        friend_needs_prefix = None
        for mapping in candidates:
            prefixes.extend(self._extract_wake_prefixes_from_mapping(mapping))
            ps = mapping.get("platform_settings")
            if isinstance(ps, dict) and friend_needs_prefix is None:
                friend_needs_prefix = ps.get("friend_message_needs_wake_prefix")
        if isinstance(friend_needs_prefix, bool):
            self._friend_needs_prefix = friend_needs_prefix
        return prefixes

    def _has_wake_prefix(self, event: AstrMessageEvent) -> bool:
        text = getattr(event, "message_str", "") or ""
        text = text.lstrip()
        for prefix in self._wake_prefixes:
            if prefix and text.startswith(prefix):
                return True
        return False

    def _is_private(self, event: AstrMessageEvent) -> bool:
        msg = getattr(event, "message_obj", None)
        gid = getattr(msg, "group_id", "")
        return not gid

    def _is_mentioning_bot(self, event: AstrMessageEvent) -> bool:
        msg = getattr(event, "message_obj", None)
        sid = str(getattr(msg, "self_id", ""))
        for seg in event.get_messages():
            if isinstance(seg, At):
                qq = str(getattr(seg, "qq", ""))
                name = str(getattr(seg, "name", ""))
                if qq and qq == sid:
                    return True
                if name and name == sid:
                    return True
        return False

    def _is_reply(self, event: AstrMessageEvent) -> bool:
        msg = getattr(event, "message_obj", None)
        raw = getattr(msg, "raw_message", None)
        if isinstance(raw, dict):
            for k in ("reply", "reply_to_message", "quote", "source"):
                if raw.get(k):
                    return True
        return False

    def _raw_contains_media(self, obj) -> bool:
        media_types = {"image", "record", "video", "file", "photo", "voice", "audio", "document"}
        if isinstance(obj, dict):
            msg = obj.get("message")
            if isinstance(msg, list):
                for seg in msg:
                    if self._raw_contains_media(seg):
                        return True
                return False

            t = obj.get("type")
            if isinstance(t, str) and t.lower() in media_types:
                return True

            msgs = obj.get("messages")
            if isinstance(msgs, list):
                for seg in msgs:
                    if self._raw_contains_media(seg):
                        return True
                return False

            data = obj.get("data")
            if isinstance(data, (dict, list)):
                return self._raw_contains_media(data)

            return False
        if isinstance(obj, list):
            for it in obj:
                if self._raw_contains_media(it):
                    return True
            return False
        return False

    def _quoted_has_media(self, event: AstrMessageEvent) -> bool:
        msg = getattr(event, "message_obj", None)
        raw = getattr(msg, "raw_message", None)
        if not isinstance(raw, dict):
            return False
        for k in ("reply", "reply_to_message", "quote", "source"):
            part = raw.get(k)
            if part and self._raw_contains_media(part):
                return True
        return False

    def _has_poke(self, event: AstrMessageEvent) -> bool:
        for seg in event.get_messages():
            if isinstance(seg, Poke):
                return True
        return False

    def _allow_llm(self, event: AstrMessageEvent) -> bool:
        if self._is_media_message(event) or self._quoted_has_media(event):
            return False
        if self._has_poke(event):
            return True
        if self._is_private(event) and not self._friend_needs_prefix:
            return True
        if self._has_wake_prefix(event):
            return True
        if self._is_mentioning_bot(event):
            return True
        if self._is_reply(event):
            return True
        return False

    def _log_block(self, event: AstrMessageEvent, stage: str, reason: str):
        msg = getattr(event, "message_obj", None)
        logger.info(
            "已屏蔽消息（无回复，停止传播）。阶段=%s 原因=%s 文档=%s 消息ID=%s 会话ID=%s 群组ID=%s 消息链=%s",
            stage,
            reason,
            "https://docs.astrbot.app/dev/star/guides/listen-message-event.html",
            getattr(msg, "message_id", None),
            getattr(msg, "session_id", None),
            getattr(msg, "group_id", None),
            event.get_messages(),
        )

    def _llm_request_contains_image_url(self, obj) -> bool:
        if isinstance(obj, dict):
            t = obj.get("type")
            if isinstance(t, str) and t.lower() == "image_url":
                return True
            if "image_url" in obj and (t is None or (isinstance(t, str) and t.lower() == "image_url")):
                return True
            for v in obj.values():
                if isinstance(v, (dict, list)) and self._llm_request_contains_image_url(v):
                    return True
            return False
        if isinstance(obj, list):
            for it in obj:
                if isinstance(it, (dict, list)) and self._llm_request_contains_image_url(it):
                    return True
            return False
        return False

    def _sanitize_llm_request(self, req) -> bool:
        changed = False

        def sanitize(obj):
            nonlocal changed

            if isinstance(obj, dict):
                t = obj.get("type")
                if isinstance(t, str) and t.lower() in {"image_url", "input_image"}:
                    obj.clear()
                    obj.update({"type": "text", "text": "[媒体内容已过滤]"})
                    changed = True
                    return

                if "image_url" in obj and (t is None or (isinstance(t, str) and t.lower() == "image_url")):
                    obj.clear()
                    obj.update({"type": "text", "text": "[媒体内容已过滤]"})
                    changed = True
                    return

                content = obj.get("content")
                if isinstance(content, list):
                    new_content = []
                    removed = 0
                    for part in content:
                        if isinstance(part, dict):
                            pt = part.get("type")
                            if isinstance(pt, str) and pt.lower() in {"image_url", "input_image"}:
                                removed += 1
                                continue
                            if "image_url" in part and (
                                pt is None or (isinstance(pt, str) and pt.lower() == "image_url")
                            ):
                                removed += 1
                                continue
                        new_content.append(part)
                    if removed:
                        changed = True
                        obj["content"] = new_content or [{"type": "text", "text": "[媒体内容已过滤]"}]

                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        sanitize(v)
                return

            if isinstance(obj, list):
                for it in obj:
                    if isinstance(it, (dict, list)):
                        sanitize(it)

        if req is None:
            return False

        if isinstance(req, (dict, list)):
            sanitize(req)
            return changed

        for attr in ("messages", "payload", "body", "data"):
            try:
                val = getattr(req, attr)
            except Exception:
                continue
            if isinstance(val, (dict, list)):
                sanitize(val)
                try:
                    setattr(req, attr, val)
                except Exception:
                    pass

        d = getattr(req, "__dict__", None)
        if isinstance(d, dict):
            sanitize(d)

        return changed

    def _result_contains_text(self, result, needle: str) -> bool:
        if not needle or result is None:
            return False
        chain = getattr(result, "chain", None)
        if not isinstance(chain, list):
            return False
        for seg in chain:
            if isinstance(seg, Plain):
                text = getattr(seg, "text", "") or ""
                if needle in text:
                    return True
                continue
            text = getattr(seg, "text", None)
            if isinstance(text, str) and needle in text:
                return True
        return False

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        prefixes = self._load_wake_prefixes_from_context()
        if prefixes:
            self._wake_prefixes = prefixes

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if self._is_media_message(event) or self._quoted_has_media(event):
            reason = "media_message" if self._is_media_message(event) else "quoted_media_message"
            self._log_block(event, "on_message", reason)
            event.stop_event()

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        get_result = getattr(event, "get_result", None)
        if callable(get_result) and get_result() is not None:
            return

        if not self._allow_llm(event):
            if self._is_media_message(event):
                reason = "media_message"
            elif self._quoted_has_media(event):
                reason = "quoted_media_message"
            else:
                reason = "no_wake_prefix_or_mention_or_reply"
            self._log_block(event, "on_llm_request", reason)
            event.stop_event()
            return

        self._sanitize_llm_request(req)
        if self._llm_request_contains_image_url(req):
            self._log_block(event, "on_llm_request", "llm_request_contains_image_url")
            event.stop_event()

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        result = event.get_result()
        if self._result_contains_text(result, "LLM 响应错误"):
            if result is not None and hasattr(result, "chain"):
                chain = getattr(result, "chain", None)
                if hasattr(chain, "clear"):
                    chain.clear()
                else:
                    setattr(result, "chain", [])
            self._log_block(event, "on_decorating_result", "llm_response_error_text")
            event.stop_event()
            return

        if not self._is_media_message(event) and not self._quoted_has_media(event):
            return
        if result is not None and hasattr(result, "chain"):
            chain = getattr(result, "chain", None)
            if hasattr(chain, "clear"):
                chain.clear()
            else:
                setattr(result, "chain", [])
        if self._is_media_message(event):
            reason = "media_message"
        elif self._quoted_has_media(event):
            reason = "quoted_media_message"
        self._log_block(event, "on_decorating_result", reason)
        event.stop_event()

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
