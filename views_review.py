"""回顾页：月历热力图、单任务时间线、周/月小结。"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import flet as ft

from db import STATUS_LABEL, STATUSES, effective_status, iso, parse_date, weekday_cn
from theme import Palette, status_color, status_text_color, tint
from widgets import card, chip, deadline_info, divider, empty_hint, section_header, status_glyph

WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")


def _month_title(d: date) -> str:
    return f"{d.year} 年 {d.month} 月"


def _day_cell(app, d: date, bucket: dict | None, p: Palette,
              first_created: date | None = None) -> ft.Control:
    today_d = date.today()
    is_today = d == today_d
    is_future = d > today_d
    bg = None
    border = None
    text_color = p.faint

    if bucket and bucket.get("count"):
        s = bucket["status"]
        bg = tint(status_color(p, s), 0.16 if not p.dark else 0.28)
        text_color = status_text_color(p, s)
    elif bucket:
        border = ft.Border.all(1, tint(status_color(p, bucket["status"]), 0.45))
        text_color = p.muted
    elif not is_future:
        text_color = p.faint

    if is_today:
        border = ft.Border.all(1.6, p.gold)
        text_color = (
            status_text_color(p, bucket["status"]) if bucket and bucket.get("count") else p.text
        )

    content: list[ft.Control] = [
        ft.Text(str(d.day), size=12,
                weight=ft.FontWeight.W_600 if is_today or (bucket and bucket.get("count"))
                else ft.FontWeight.W_400,
                color=text_color)
    ]
    if bucket and bucket.get("backfill"):
        content.append(
            ft.Container(width=3, height=3, border_radius=2, bgcolor=p.gold)
        )

    if bucket:
        tip = f"{d.month}月{d.day}日 · {STATUS_LABEL[bucket['status']]}"
        if bucket.get("count"):
            tip += f" · {bucket['count']} 条记录"
        if bucket.get("backfill"):
            tip += " · 含补记"
    elif first_created and d < first_created:
        tip = f"{d.month}月{d.day}日 · 还没有任务"
    else:
        tip = f"{d.month}月{d.day}日 · {'待打卡' if is_today else ('未开始' if is_future else '未记录')}"

    return ft.Container(
        content=ft.Column(content, spacing=2, tight=True, alignment=ft.MainAxisAlignment.CENTER,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        expand=True,
        height=44,
        border_radius=10,
        bgcolor=bg,
        border=border,
        alignment=ft.Alignment.CENTER,
        on_click=lambda e, day=d: app.open_day(day),
        tooltip=tip,
    )


def _calendar_card(app) -> ft.Control:
    p: Palette = app.palette
    month: date = app.review_month
    buckets = app.db.month_map(month.year, month.month)

    nav = ft.Row(
        [
            ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_size=18, icon_color=p.muted,
                          on_click=lambda e: app.shift_month(-1), tooltip="上个月"),
            ft.Text(_month_title(month), size=15, weight=ft.FontWeight.W_600, color=p.text, expand=True,
                    text_align=ft.TextAlign.CENTER),
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_size=18, icon_color=p.muted,
                          on_click=lambda e: app.shift_month(1), tooltip="下个月"),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    grid: list[ft.Control] = [
        ft.Row(
            [ft.Text(w, size=11, color=p.muted, expand=True, text_align=ft.TextAlign.CENTER)
             for w in WEEKDAYS],
            spacing=6,
        )
    ]

    first = date(month.year, month.month, 1)
    days = calendar.monthrange(month.year, month.month)[1]
    first_created = min(
        (parse_date(t["created_at"]) for t in app.db.list_tasks()), default=None
    )
    cells: list[ft.Control] = [ft.Container(expand=True, height=44) for _ in range(first.weekday())]
    for day_num in range(1, days + 1):
        d = date(month.year, month.month, day_num)
        cells.append(_day_cell(app, d, buckets.get(iso(d)), p, first_created))
        if len(cells) == 7:
            grid.append(ft.Row(cells, spacing=6))
            cells = []
    if cells:
        while len(cells) < 7:
            cells.append(ft.Container(expand=True, height=44))
        grid.append(ft.Row(cells, spacing=6))

    legend_items = []
    for s in ("perfect", "smooth", "hard", "pain", "missed", "pending"):
        legend_items.append(
            ft.Row(
                [status_glyph(s, p, 13, show_tooltip=False),
                 ft.Text(STATUS_LABEL[s], size=10, color=p.muted)],
                spacing=4,
                tight=True,
            )
        )

    return card(
        ft.Column(
            [
                nav,
                ft.Column(grid, spacing=6, tight=True),
                divider(p),
                ft.Row(legend_items, wrap=True, spacing=12, run_spacing=6),
                ft.Text("点击任意一天，可以补记或修改那天的记录。", size=10, color=p.faint),
            ],
            spacing=10,
            tight=True,
        ),
        p,
    )


def _timeline_cell(app, d: date, record: dict | None, p: Palette,
                   created: date | None = None) -> ft.Control:
    if record is None and created and d < created:
        return ft.Container(
            width=16, height=18,
            content=ft.Container(width=16, height=16, border_radius=4, bgcolor=p.surface_soft),
            tooltip=f"{d.month}月{d.day}日 · 任务还没开始",
        )
    status = effective_status(record, d)
    parts: list[ft.Control] = []
    if status in ("pending", "missed"):
        parts.append(
            ft.Container(
                width=16, height=16, border_radius=4,
                border=ft.Border.all(1.4, status_color(p, status)),
            )
        )
    else:
        parts.append(ft.Container(width=16, height=16, border_radius=4,
                                  bgcolor=status_color(p, status)))
    if record and record.get("is_backfill"):
        parts.append(
            ft.Container(
                width=16, height=16, alignment=ft.Alignment.BOTTOM_RIGHT,
                content=ft.Container(width=5, height=5, border_radius=3, bgcolor=p.surface),
            )
        )

    return ft.Container(
        content=ft.Stack(parts, width=16, height=16),
        width=16,
        height=18,
        on_click=lambda e, day=d: app.open_day(day),
        tooltip=f"{d.month}月{d.day}日 · {STATUS_LABEL[status]}" + ("（补记）" if record and record["is_backfill"] else ""),
    )


def _timeline_card(app) -> ft.Control:
    p: Palette = app.palette
    tasks = app.db.list_tasks(include_archived=True)
    if not tasks:
        return card(empty_hint("还没有任务，时间线会在有记录后出现。", p), p)

    ids = {t["id"] for t in tasks}
    if app.timeline_task_id not in ids:
        app.timeline_task_id = tasks[0]["id"]
    task = next(t for t in tasks if t["id"] == app.timeline_task_id)

    dropdown = ft.Dropdown(
        value=str(task["id"]),
        options=[ft.DropdownOption(key=str(t["id"]), text=t["name"]) for t in tasks],
        on_select=lambda e: app.set_timeline_task(int(e.control.value)),
        border_radius=12,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        text_size=13,
        expand=True,
    )

    end = date.today()
    start = end - timedelta(days=29)
    created = parse_date(task["created_at"])
    cells = [app.db.get_checkin(task["id"], start + timedelta(days=i)) for i in range(30)]
    days = [start + timedelta(days=i) for i in range(30)]

    timeline = ft.Row(
        [_timeline_cell(app, days[i], cells[i], p, created) for i in range(30)],
        wrap=True,
        spacing=6,
        run_spacing=6,
    )

    stats = app.db.task_stats(task["id"], 30)
    counts = stats["counts"]
    chips: list[ft.Control] = [
        chip("记录 %d 次" % stats["records"], p, color=p.text),
    ]
    for s in STATUSES:
        if counts[s]:
            chips.append(chip(f"{STATUS_LABEL[s]} {counts[s]}", p,
                              color=status_text_color(p, s),
                              bgcolor=tint(status_color(p, s), 0.10)))
    if stats["backfill"]:
        chips.append(chip(f"补记 {stats['backfill']}", p, color=p.gold,
                          bgcolor=tint(p.gold, 0.10)))
    chips.append(chip(f"最长连续 {stats['streak']} 天", p, color=p.muted))

    info = deadline_info(task.get("deadline")) if task["type"] == "special" else None
    meta = "近 30 天 · " + ("特殊任务" if task["type"] == "special" else "普通任务")
    if info:
        meta += f" · {info[0]}"

    return card(
        ft.Column(
            [
                section_header("单任务时间线", p, meta),
                ft.Row([dropdown], spacing=0),
                timeline,
                ft.Row(chips, wrap=True, spacing=6, run_spacing=6),
            ],
            spacing=12,
            tight=True,
        ),
        p,
    )


def _narrative(label: str, s: dict) -> str:
    if s["records"] == 0:
        return f"{label}还没有记录，留白也算一种节奏。"
    text = f"{label}你留下了 {s['records']} 次记录"
    if s["counts"]["perfect"]:
        text += f"，其中 {s['counts']['perfect']} 次是完美"
    text += "。"
    return text


def _summary_card(app, label: str, start: date, end: date) -> ft.Control:
    p: Palette = app.palette
    s = app.db.period_summary(start, end)
    chips: list[ft.Control] = []
    for st in STATUSES:
        chips.append(chip(f"{STATUS_LABEL[st]} {s['counts'][st]}", p,
                          color=status_text_color(p, st),
                          bgcolor=tint(status_color(p, st), 0.10)))
    if s["missed"]:
        chips.append(chip(f"未记录 {s['missed']}", p, color=p.muted,
                          border_color=tint(p.missed, 0.35)))
    if s["streak"]:
        chips.append(chip(f"最长连续 {s['streak']} 天", p, color=p.text, bgcolor=p.surface_soft))
    if s["special"]:
        chips.append(chip(f"特殊任务 {s['special']} 次", p, color=p.gold,
                          bgcolor=tint(p.gold, 0.10)))

    range_text = f"{start.month}.{start.day} - {end.month}.{end.day}"
    return card(
        ft.Column(
            [
                section_header(label, p, range_text),
                ft.Text(_narrative(label, s), size=13, color=p.text),
                ft.Row(chips, wrap=True, spacing=6, run_spacing=6),
            ],
            spacing=12,
            tight=True,
        ),
        p,
    )


def build_review(app) -> ft.Control:
    p: Palette = app.palette
    t = date.today()
    week_start = t - timedelta(days=t.weekday())
    month_start = t.replace(day=1)

    header = ft.Column(
        [
            ft.Text("回顾", size=28, weight=ft.FontWeight.W_700, color=p.text),
            ft.Text("历史不是报表，是你这一周过得怎么样。", size=12, color=p.muted),
        ],
        spacing=4,
        tight=True,
    )

    return ft.Column(
        [
            header,
            _calendar_card(app),
            _timeline_card(app),
            _summary_card(app, "本周", week_start, week_start + timedelta(days=6)),
            _summary_card(app, "本月", month_start, t),
        ],
        spacing=18,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
