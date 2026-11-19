"""今日页。"""

from __future__ import annotations

from datetime import date, datetime

import flet as ft

from db import STATUS_LABEL, STATUSES, effective_status, weekday_cn
from theme import Palette, status_color, status_text_color, tint
from widgets import card, deadline_info, divider, empty_hint, section_header, status_glyph

GREETINGS = (
    (5, "夜深了，轻轻记一笔就好。"),
    (11, "早上好，从一件小事开始。"),
    (14, "中午好，慢慢来就好。"),
    (18, "下午好，留下一点痕迹。"),
    (24, "晚上好，今天也辛苦了。"),
)


def greeting(hour: int) -> str:
    for limit, text in GREETINGS:
        if hour < limit:
            return text
    return GREETINGS[-1][1]


def task_row(app, task: dict, d: date, checkin: dict | None, status: str) -> ft.Control:
    p: Palette = app.palette
    is_special = task["type"] == "special"
    color = status_color(p, status)

    name_row: list[ft.Control] = []
    if is_special:
        name_row.append(ft.Icon(ft.Icons.STAR_ROUNDED, size=14, color=p.gold))
    name_row.append(
        ft.Text(task["name"], size=15, weight=ft.FontWeight.W_600, color=p.text,
                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)
    )

    sub_parts: list[str] = []
    if task.get("reminder_time"):
        if task.get("reminder_enabled"):
            sub_parts.append(f"{task['reminder_time']} 提醒")
        else:
            sub_parts.append(f"{task['reminder_time']}（提醒未开）")
    if is_special:
        info = deadline_info(task.get("deadline"))
        if info:
            sub_parts.append(info[0])
    if checkin and checkin["is_backfill"]:
        sub_parts.append("补记")
    if checkin and checkin.get("note"):
        sub_parts.append(f"“{checkin['note']}”")

    body: list[ft.Control] = [ft.Row(name_row, spacing=6, tight=True)]
    if sub_parts:
        body.append(ft.Text(" · ".join(sub_parts), size=11, color=p.muted,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))

    pill_text = "记录" if status == "pending" else STATUS_LABEL[status]
    pill_color = status_text_color(p, status)
    pill = ft.Container(
        content=ft.Text(pill_text, size=11, weight=ft.FontWeight.W_600, color=pill_color),
        alignment=ft.Alignment.CENTER,
        height=30,
        width=50,
        border_radius=999,
        bgcolor=tint(status_color(p, status), 0.10) if status != "pending" else None,
        border=ft.Border.all(1, tint(status_color(p, status), 0.30)),
    )

    return ft.Container(
        content=ft.Row(
            [
                status_glyph(status, p, 26, backfill=bool(checkin and checkin["is_backfill"])),
                ft.Column(body, spacing=3, tight=True, expand=True),
                pill,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=14, vertical=13),
        border_radius=16,
        bgcolor=tint(p.gold, 0.05 if not p.dark else 0.09) if is_special else p.surface,
        border=ft.Border.all(1.3 if is_special else 1, tint(p.gold, 0.55) if is_special else p.line),
        on_click=lambda e: app.open_checkin(task, d),
    )


def build_today(app) -> ft.Control:
    p: Palette = app.palette
    d = date.today()
    tasks = app.db.list_tasks()
    checkins = app.db.day_checkins(d)
    statuses = {t["id"]: effective_status(checkins.get(t["id"]), d) for t in tasks}
    recorded = sum(1 for s in statuses.values() if s in STATUSES)

    now = datetime.now()
    app.clock_text = ft.Text(now.strftime("%H:%M"), size=13, weight=ft.FontWeight.W_600, color=p.muted)

    header = ft.Row(
        [
            ft.Column(
                [
                    ft.Text(f"{d.month}月{d.day}日 · 星期{weekday_cn(d)}", size=12, color=p.muted),
                    ft.Text("今天", size=30, weight=ft.FontWeight.W_700, color=p.text),
                ],
                spacing=2,
                tight=True,
                expand=True,
            ),
            ft.Column(
                [app.clock_text, ft.Text(greeting(now.hour), size=11, color=p.muted)],
                spacing=2,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.END,
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.END,
    )

    if tasks:
        caption = f"{recorded}/{len(tasks)} 已记录"
        progress_value = recorded / len(tasks)
    else:
        caption = "还没有任务"
        progress_value = 0.0

    progress = card(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(caption, size=13, weight=ft.FontWeight.W_600, color=p.text),
                        ft.Text(
                            "全部记下了" if tasks and recorded == len(tasks) else "打开即记录",
                            size=11,
                            color=p.muted,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [
                        ft.ProgressBar(
                            value=progress_value,
                            bar_height=5,
                            color=p.gold,
                            bgcolor=p.line,
                            border_radius=3,
                            expand=True,
                        )
                    ],
                    spacing=0,
                ),
            ],
            spacing=10,
            tight=True,
        ),
        p,
        padding=14,
    )

    sections: list[ft.Control] = [header, progress]

    specials = [t for t in tasks if t["type"] == "special"]
    normals = [t for t in tasks if t["type"] == "normal"]

    if specials:
        sections.append(
            ft.Column(
                [
                    section_header("特殊任务", p, "置顶 · 带截止日期"),
                    ft.Column([task_row(app, t, d, checkins.get(t["id"]),
                                         statuses[t["id"]]) for t in specials], spacing=8),
                ],
                spacing=10,
                tight=True,
            )
        )
    if normals:
        sections.append(
            ft.Column(
                [
                    section_header("今日任务", p, f"{len(normals)} 个"),
                    ft.Column([task_row(app, t, d, checkins.get(t["id"]),
                                         statuses[t["id"]]) for t in normals], spacing=8),
                ],
                spacing=10,
                tight=True,
            )
        )
    if not tasks:
        sections.append(
            card(
                empty_hint(
                    "还没有任务。\n先添加一个想坚持的小事，明天再回来看颜色。",
                    p,
                    ft.OutlinedButton("添加第一个任务", icon=ft.Icons.ADD,
                                      on_click=lambda e: app.open_task_editor()),
                ),
                p,
            )
        )

    sections.append(divider(p, 1))
    sections.append(
        ft.Text("点击任务，记录今天的感觉。未记录不是失败，只是那天没有留下颜色。",
                size=11, color=p.faint)
    )

    return ft.Column(sections, spacing=18, scroll=ft.ScrollMode.AUTO, expand=True)
