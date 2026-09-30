"""Preview helper: show text the way WhatsApp renders *bold*, _italic_, ~strike~ and ```mono```."""
import html
import re

_MONO = re.compile(r"```(.+?)```", re.S)
_B = re.compile(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])")
_I = re.compile(r"(?<![\w_])_(?![\s_])(.+?)(?<![\s_])_(?![\w_])")
_S = re.compile(r"(?<![\w~])~(?![\s~])(.+?)(?<![\s~])~(?![\w~])")


def to_html(text: str) -> str:
    out = html.escape(text, quote=False)
    mono: list[str] = []

    def keep(m):
        mono.append(m.group(1))
        return f"\x01{len(mono) - 1}\x01"

    out = _MONO.sub(keep, out)
    out = "\n".join(_S.sub(r"<s>\1</s>", _I.sub(r"<i>\1</i>", _B.sub(r"<b>\1</b>", ln))) for ln in out.split("\n"))
    for i, m in enumerate(mono):
        out = out.replace(f"\x01{i}\x01", f"<span style=\"font-family:Consolas\">{m}</span>")
    out = re.sub(r" {2,}", lambda m: "&nbsp;" * len(m.group(0)), out)
    return out.replace("\n", "<br>")
