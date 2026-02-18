from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Image, Record, Video, File as FileComponent, At, Poke
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("image_message_filter", "YourName", "过滤图片消息的插件", "1.0.0")
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

    def _has_poke(self, event: AstrMessageEvent) -> bool:
        for seg in event.get_messages():
            if isinstance(seg, Poke):
                return True
        return False

    def _allow_llm(self, event: AstrMessageEvent) -> bool:
        if self._is_media_message(event):
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

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        prefixes = self._load_wake_prefixes_from_context()
        if prefixes:
            self._wake_prefixes = prefixes

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if self._is_media_message(event):
            self._log_block(event, "on_message", "media_message")
            event.stop_event()

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        if not self._allow_llm(event):
            reason = "media_message" if self._is_media_message(event) else "no_wake_prefix_or_mention_or_reply"
            self._log_block(event, "on_llm_request", reason)
            event.stop_event()

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        if self._allow_llm(event):
            return
        result = event.get_result()
        if result is not None and hasattr(result, "chain"):
            chain = getattr(result, "chain", None)
            if hasattr(chain, "clear"):
                chain.clear()
            else:
                setattr(result, "chain", [])
        reason = "media_message" if self._is_media_message(event) else "no_wake_prefix_or_mention_or_reply"
        self._log_block(event, "on_decorating_result", reason)
        event.stop_event()

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
