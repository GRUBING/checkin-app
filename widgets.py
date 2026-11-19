"""通用视觉组件：状态形状、卡片、标签、Toast。"""

from __future__ import annotations

from datetime import date

import flet as ft

from theme import Palette, status_color, tint

STATUS_ICON = {
    "perfect": ft.Icons.STAR_ROUNDED,
    "smooth": ft.Icons.CHECK_ROUNDED,
    "hard": ft.Icons.REMOVE_ROUNDED,
    "pain": ft.Icons.CLOSE_ROUNDED,
}


def status_glyph(status: str, p: Palette, size: int = 26, backfill: bool = False,
                 show_tooltip: bool = True) -> ft.Control:
    """状态形状：实心=已记录，空心=待打卡，空心+斜线=未记录。"""
    color = status_color(p, status)
    if status in ("pending", "missed"):
        parts: list[ft.Control] = [
            ft.Container(width=size, height=size, border_radius=size / 2,
                         border=ft.Border.all(1.6, color))
        ]
        if status == "missed":
            parts.append(
                ft.Container(width=size * 0.74, height=1.7, border_radius=2,
                             bgcolor=color, rotate=ft.Rotate(angle=-0.785))
            )
        glyph: ft.Control = ft.Stack(parts, width=size, height=size, alignment=ft.Alignment.CENTER)
    else:
        glyph = ft.Stack(
            [
                ft.Container(width=size, height=size, border_radius=size / 2, bgcolor=color),
                ft.Icon(STATUS_ICON[status], size=size * 0.6, color="#FFFFFF"),
            ],
            width=size,
            height=size,
            alignment=ft.Alignment.CENTER,
        )
    if backfill:
        glyph = ft.Stack(
            [
                glyph,
                ft.Container(
                    width=size,
                    height=size,
                    alignment=ft.Alignment.BOTTOM_RIGHT,
                    content=ft.Container(
                        width=9, height=9, border_radius=5,
                        bgcolor=p.gold, border=ft.Border.all(1.5, p.surface),
                    ),
                ),
            ],
            width=size,
            height=size,
        )
    labels = {
        "perfect": "完美", "smooth": "顺利", "hard": "艰难",
        "pain": "痛苦", "missed": "未记录", "pending": "待打卡",
    }
    return ft.Container(glyph, tooltip=labels.get(status, "") if show_tooltip else None)


def card(content: ft.Control, p: Palette, padding: int = 16, radius: int = 20,
         bgcolor: str | None = None, border_color: str | None = None,
         on_click=None, shadow: bool = True) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        border_radius=radius,
        bgcolor=bgcolor or p.surface,
        border=ft.Border.all(1, border_color or p.line),
        shadow=(
            ft.BoxShadow(
                blur_radius=18,
                spread_radius=0,
                color=tint(p.shadow, 0.04 if not p.dark else 0.35),
                offset=ft.Offset(0, 6),
            )
            if shadow
            else None
        ),
        on_click=on_click,
    )


def chip(text: str, p: Palette, color: str | None = None, bgcolor: str | None = None,
         border_color: str | None = None, size: int = 11, icon: ft.IconData | None = None) -> ft.Container:
    color = color or p.muted
    inner: ft.Control
    if icon:
        inner = ft.Row(
            [
                ft.Icon(icon, size=size + 2, color=color),
                ft.Text(text, size=size, color=color, weight=ft.FontWeight.W_500),
            ],
            spacing=4,
            tight=True,
        )
    else:
        inner = ft.Text(text, size=size, color=color, weight=ft.FontWeight.W_500)
    return ft.Container(
        content=inner,
        padding=ft.Padding.symmetric(horizontal=9, vertical=4),
        border_radius=999,
        bgcolor=bgcolor,
        border=ft.Border.all(1, border_color) if border_color else None,
    )


def section_header(title: str, p: Palette, hint: str | None = None,
                   trailing: ft.Control | None = None) -> ft.Control:
    left: list[ft.Control] = [
        ft.Text(title, size=15, weight=ft.FontWeight.W_600, color=p.text)
    ]
    if hint:
        left.append(ft.Text(hint, size=11, color=p.muted))
    return ft.Row(
        [
            ft.Column(left, spacing=2, tight=True, expand=True),
            trailing or ft.Container(),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def divider(p: Palette, height: int = 1) -> ft.Container:
    return ft.Container(height=height, bgcolor=p.line)


def toast(page: ft.Page, message: str) -> None:
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(message, size=13, color="#FFFFFF"),
            bgcolor="#2A2E2B",
            duration=1800,
        )
    )


def deadline_info(deadline: str | None) -> tuple[str, bool] | None:
    """返回 (文案, 是否紧迫)。"""
    if not deadline:
        return None
    try:
        d = date.fromisoformat(deadline[:10])
    except ValueError:
        return None
    delta = (d - date.today()).days
    if delta > 0:
        return (f"还剩 {delta} 天", delta <= 2)
    if delta == 0:
        return ("今天截止", True)
    return (f"已过截止 {abs(delta)} 天", False)


def empty_hint(text: str, p: Palette, action: ft.Control | None = None) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Text(text, size=13, color=p.muted, text_align=ft.TextAlign.CENTER)
    ]
    if action:
        controls.append(action)
    return ft.Container(
        content=ft.Column(controls, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=28),
        alignment=ft.Alignment.CENTER,
    )


def screen_title(title: str, p: Palette, subtitle: str | None = None,
                 trailing: ft.Control | None = None) -> ft.Control:
    left: list[ft.Control] = [
        ft.Text(title, size=28, weight=ft.FontWeight.W_700, color=p.text)
    ]
    if subtitle:
        left.append(ft.Text(subtitle, size=12, color=p.muted))
    return ft.Row(
        [ft.Column(left, spacing=4, tight=True, expand=True), trailing or ft.Container()],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.END,
    )
