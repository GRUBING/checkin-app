"""配色与视觉常量。颜色永远配合形状/图标，避免只靠颜色传达语义。"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    surface: str
    surface_soft: str
    text: str
    muted: str
    faint: str
    line: str
    gold: str
    perfect: str
    smooth: str
    hard: str
    pain: str
    missed: str
    pending: str
    shadow: str


LIGHT = Palette(
    dark=False,
    bg="#F4F3EF",
    surface="#FFFFFF",
    surface_soft="#FAF9F5",
    text="#1D201E",
    muted="#8B9089",
    faint="#B9BDB6",
    line="#EAE7DF",
    gold="#C8901E",
    perfect="#F2B200",
    smooth="#2FA84F",
    hard="#EF8B00",
    pain="#8B0000",
    missed="#FF3B30",
    pending="#A5AAA3",
    shadow="#1D201E",
)

DARK = Palette(
    dark=True,
    bg="#0E100F",
    surface="#171A18",
    surface_soft="#1D211E",
    text="#F1F2EE",
    muted="#9AA09A",
    faint="#6F756F",
    line="#272C28",
    gold="#E5B347",
    perfect="#FFC94D",
    smooth="#3ED46F",
    hard="#FFA733",
    pain="#C22A2A",
    missed="#FF6B61",
    pending="#7E847E",
    shadow="#000000",
)

STATUS_TEXT_LIGHT = {
    "perfect": "#8A5E00",
    "smooth": "#1E7A3D",
    "hard": "#8A5200",
    "pain": "#7A0B0B",
    "missed": "#C2352C",
    "pending": "#8B9089",
}

STATUS_DESC = {
    "perfect": "状态极佳",
    "smooth": "稳定完成",
    "hard": "有点吃力",
    "pain": "咬牙撑过",
}


def palette_for(dark: bool) -> Palette:
    return DARK if dark else LIGHT


def status_color(p: Palette, status: str) -> str:
    return {
        "perfect": p.perfect,
        "smooth": p.smooth,
        "hard": p.hard,
        "pain": p.pain,
        "missed": p.missed,
        "pending": p.pending,
    }.get(status, p.muted)


def status_text_color(p: Palette, status: str) -> str:
    if p.dark:
        return status_color(p, status)
    return STATUS_TEXT_LIGHT.get(status, p.muted)


def tint(color: str, alpha: float) -> str:
    return ft.Colors.with_opacity(alpha, color)
