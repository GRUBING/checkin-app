"""回顾页：月历热力图、任务时间线、周/月小结与多任务柱状图。"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import flet as ft

from db import STATUS_LABEL, STATUSES, effective_status, iso, parse_date, weekday_cn
from theme import Palette, status_color, status_text_color, tint
from widgets import card, chip, deadline_info, divider, empty_hint, section_header, status_glyph

WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")
ALL = "all"
BAR_PARTS = ("perfect", "smooth", "hard", "pain", "missed", "pending")


def _month_title(d: date) -> str:
    return f"{d.year} 年 {d.month} 月"


def _segment_color(p: Palette, status: str) -> str:
    """柱状图/日历色条颜色：未记录用浅灰，待打卡用中灰。"""
    if status == "missed":
        return tint(p.pending, 0.30)
    if status == "pending":
        return tint(p.pending, 0.62)
    return status_color(p, status)


def _parts_bar(parts: dict[str, int], p: Palette, width: int = 26,
               height: int = 4) -> ft.Control:
    segments: list[ft.Control] = []
    for st in BAR_PARTS:
        n = parts.get(st, 0)
        if not n:
            continue
        segments.append(
            ft.Container(
                expand=n,
                bgcolor=_segment_color(p, st),
                tooltip=f"{STATUS_LABEL[st]} {n}",
            )
        )
    return ft.Container(
        width=width,
        height=height,
        border_radius=height / 2,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Row(segments, spacing=0, tight=True),
    )


def _day_cell(app, d: date, bucket: dict | None, p: Palette,
              first_created: date | None = None, show_parts: bool = False) -> ft.Control:
    today_d = date.today()
    is_today = d == today_d
    is_future = d > today_d
    bg = None
    border = None
    text_color = p.faint

    if bucket and bucket.get("count"):
        s = bucket["status"]
        if show_parts:
            bg = p.surface_soft
            text_color = p.text
        else:
            bg = tint(status_color(p, s), 0.16 if not p.dark else 0.28)
            text_color = status_text_color(p, s)
    elif bucket:
        if show_parts:
            bg = p.surface_soft
            text_color = p.text if bucket.get("parts", {}).get("pending") else p.muted
        else:
            border = ft.Border.all(1, tint(status_color(p, bucket["status"]), 0.45))
            text_color = p.muted
    elif not is_future:
        text_color = p.faint

    if is_today:
        border = ft.Border.all(1.6, p.gold)
        text_color = (
            status_text_color(p, bucket["status"]) if bucket and bucket.get("count") and not show_parts
            else p.text
        )

    content: list[ft.Control] = [
        ft.Text(str(d.day), size=12,
                weight=ft.FontWeight.W_600 if is_today or (bucket and bucket.get("count"))
                else ft.FontWeight.W_400,
                color=text_color)
    ]
    if bucket and show_parts and bucket.get("parts"):
        content.append(_parts_bar(bucket["parts"], p))
    if bucket and bucket.get("backfill") and not show_parts:
        content.append(
            ft.Container(width=3, height=3, border_radius=2, bgcolor=p.gold)
        )

    if bucket:
        tip = f"{d.month}月{d.day}日"
        if bucket.get("parts"):
            detail = " · ".join(
                f"{STATUS_LABEL[s]}{bucket['parts'][s]}"
                for s in BAR_PARTS if bucket["parts"].get(s)
            )
            tip += f" · {detail}"
        else:
            tip += f" · {STATUS_LABEL[bucket['status']]}"
        if bucket.get("backfill"):
            tip += " · 含补记"
    elif first_created and d < first_created:
        tip = f"{d.month}月{d.day}日 · 还没有任务"
    else:
        tip = f"{d.month}月{d.day}日 · {'待打卡' if is_today else ('未开始' if is_future else '未记录')}"

    return ft.Container(
        content=ft.Column(content, spacing=3, tight=True, alignment=ft.MainAxisAlignment.CENTER,
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
    all_mode = app.timeline_task_id == ALL
    tasks = app.db.list_tasks(include_archived=True)
    task = None
    if not all_mode:
        task = next((t for t in tasks if t["id"] == app.timeline_task_id), None)
        if task is None:
            all_mode = True
    buckets = app.db.month_map(
        month.year, month.month, None if all_mode else int(app.timeline_task_id)
    )

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

    if all_mode:
        scope = (
            f"全部任务 · {len(tasks)} 个任务 · 色条是当天各任务的状态组成"
            if tasks else "全部任务"
        )
    else:
        scope = f"{task['name']} · 单任务视图"

    grid: list[ft.Control] = [
        ft.Row(
            [ft.Text(w, size=11, color=p.muted, expand=True, text_align=ft.TextAlign.CENTER)
             for w in WEEKDAYS],
            spacing=6,
        )
    ]

    first = date(month.year, month.month, 1)
    days = calendar.monthrange(month.year, month.month)[1]
    first_created = min((parse_date(t["created_at"]) for t in tasks), default=None)
    cells: list[ft.Control] = [ft.Container(expand=True, height=44) for _ in range(first.weekday())]
    for day_num in range(1, days + 1):
        d = date(month.year, month.month, day_num)
        cells.append(_day_cell(app, d, buckets.get(iso(d)), p, first_created, show_parts=all_mode))
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
                ft.Text(scope, size=10, color=p.muted, no_wrap=True, max_lines=1),
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


def _stat_chips(app, s: dict, p: Palette, with_special: bool = True) -> list[ft.Control]:
    chips: list[ft.Control] = [chip("记录 %d 次" % s["records"], p, color=p.text)]
    for st in STATUSES:
        if s["counts"][st]:
            chips.append(chip(f"{STATUS_LABEL[st]} {s['counts'][st]}", p,
                              color=status_text_color(p, st),
                              bgcolor=tint(status_color(p, st), 0.10)))
    if s.get("missed"):
        chips.append(chip(f"未记录 {s['missed']}", p, color=p.muted,
                          border_color=tint(p.missed, 0.35)))
    if s.get("backfill"):
        chips.append(chip(f"补记 {s['backfill']}", p, color=p.gold,
                          bgcolor=tint(p.gold, 0.10)))
    if s.get("streak"):
        chips.append(chip(f"最长连续 {s['streak']} 天", p, color=p.muted))
    if with_special and s.get("special"):
        chips.append(chip(f"特殊任务 {s['special']} 次", p, color=p.gold,
                          bgcolor=tint(p.gold, 0.10)))
    return chips


def _timeline_card(app) -> ft.Control:
    p: Palette = app.palette
    tasks = app.db.list_tasks(include_archived=True)
    if not tasks:
        return card(empty_hint("还没有任务，时间线会在有记录后出现。", p), p)

    ids = {t["id"] for t in tasks}
    if app.timeline_task_id != ALL and app.timeline_task_id not in ids:
        app.timeline_task_id = ALL
    all_mode = app.timeline_task_id == ALL

    dropdown = ft.Dropdown(
        value=ALL if all_mode else str(app.timeline_task_id),
        options=[ft.DropdownOption(key=ALL, text="全部任务")] + [
            ft.DropdownOption(key=str(t["id"]), text=t["name"]) for t in tasks
        ],
        on_select=lambda e: app.set_timeline_task(e.control.value),
        border_radius=12,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        text_size=13,
        expand=True,
    )

    end = date.today()
    start = end - timedelta(days=29)

    if all_mode:
        s = app.db.period_summary(start, end)
        return card(
            ft.Column(
                [
                    section_header("全部任务总览", p, f"近 30 天 · {len(tasks)} 个任务"),
                    ft.Row([dropdown], spacing=0),
                    ft.Text("已选择全部任务：上方日历按每天的任务状态组成着色，"
                            "下方「本周 / 本月」显示多色柱状图。",
                            size=11, color=p.muted),
                    ft.Row(_stat_chips(app, s, p), wrap=True, spacing=6, run_spacing=6),
                ],
                spacing=12,
                tight=True,
            ),
            p,
        )

    task = next(t for t in tasks if t["id"] == app.timeline_task_id)
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
                ft.Row(_stat_chips(app, stats, p, with_special=False), wrap=True,
                       spacing=6, run_spacing=6),
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


def _short_name(name: str, limit: int = 5) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


def _composition_chart(app, start: date, end: date) -> ft.Control:
    """每天一根多色柱：从下到上依次对应任务 1..N，颜色为当天状态。"""
    p: Palette = app.palette
    today_d = date.today()
    end = min(end, today_d)
    if start > end:
        return empty_hint("这段时间还没有开始。", p)

    raw = app.db.status_by_task_day(start, end)
    tasks = [
        t for t in app.db.list_tasks(include_archived=True)
        if parse_date(t["created_at"]) <= end and (not t["archived"] or raw.get(int(t["id"])))
    ]
    if not tasks:
        return empty_hint("这段时间还没有记录，打个卡再回来看。", p)

    days: list[date] = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)

    day_count = len(days)
    n = len(tasks)
    seg_h = max(9, min(18, 132 // n))
    bar_w = 18 if day_count <= 10 else 13
    spacing = 4 if day_count <= 10 else 2
    show_names = getattr(app, "review_name_tasks", set())

    y_items: list[ft.Control] = []
    for i, t in enumerate(tasks):
        shown = int(t["id"]) in show_names
        y_items.append(
            ft.Container(
                width=48,
                height=seg_h,
                alignment=ft.Alignment.CENTER_LEFT,
                on_click=lambda e, tid=int(t["id"]): app.toggle_task_label(tid),
                tooltip=t["name"],
                content=ft.Text(
                    _short_name(t["name"], 7) if shown else f"任务{i + 1}",
                    size=9,
                    color=p.text if shown else p.muted,
                    no_wrap=True,
                    max_lines=1,
                ),
            )
        )

    columns: list[ft.Control] = []
    for day in days:
        segments: list[ft.Control] = []
        for t in tasks:
            row = raw.get(int(t["id"]), {}).get(iso(day))
            if row:
                st = row["status"]
            elif t["archived"] or day < parse_date(t["created_at"]):
                st = None
            else:
                st = "pending" if day == today_d else "missed"
            segments.append(
                ft.Container(
                    width=bar_w,
                    height=seg_h,
                    bgcolor=ft.Colors.TRANSPARENT if st is None else _segment_color(p, st),
                    tooltip=None if st is None else
                    f"{day.month}月{day.day}日 · {t['name']} · {STATUS_LABEL[st]}",
                )
            )
        is_today = day == today_d
        label = f"周{weekday_cn(day)}" if day_count <= 10 else str(day.day)
        columns.append(
            ft.Column(
                [
                    ft.Container(
                        width=bar_w,
                        height=seg_h * n,
                        border_radius=4,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        content=ft.Column(segments, spacing=0, tight=True),
                    ),
                    ft.Text(label, size=9,
                            color=p.gold if is_today else p.muted,
                            weight=ft.FontWeight.W_700 if is_today else ft.FontWeight.W_400,
                            no_wrap=True, max_lines=1),
                ],
                spacing=4,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    chart = ft.Container(
        content=ft.Row(
            [
                ft.Column(y_items + [ft.Container(height=17)], spacing=0, tight=True),
                ft.Row(columns, spacing=spacing, scroll=ft.ScrollMode.AUTO, expand=True),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.symmetric(horizontal=8, vertical=10),
        bgcolor=p.surface_soft,
        border_radius=14,
    )

    legend = ft.Row(
        [
            ft.Row(
                [ft.Container(width=8, height=8, border_radius=2,
                              bgcolor=_segment_color(p, st)),
                 ft.Text(STATUS_LABEL[st], size=9, color=p.muted)],
                spacing=4,
                tight=True,
            )
            for st in ("perfect", "smooth", "hard", "pain", "missed")
        ],
        wrap=True,
        spacing=10,
        run_spacing=5,
    )

    hint = "柱子从下到上对应左侧任务 1、2、3…，颜色是那天的状态；点击编号显示任务名称。"
    if day_count > 16:
        hint = "左右滑动查看整月 · " + hint

    return ft.Column(
        [chart, legend, ft.Text(hint, size=10, color=p.faint)],
        spacing=8,
        tight=True,
    )


def _summary_card(app, label: str, start: date, end: date) -> ft.Control:
    p: Palette = app.palette
    all_mode = app.timeline_task_id == ALL
    if all_mode:
        s = app.db.period_summary(start, end)
    else:
        s = app.db.task_period_summary(int(app.timeline_task_id), start, end)

    range_text = f"{start.month}.{start.day} - {end.month}.{end.day}"
    body: list[ft.Control] = [
        section_header(label, p, range_text),
        ft.Text(_narrative(label, s), size=13, color=p.text),
    ]
    if all_mode:
        body.append(_composition_chart(app, start, end))
    body.append(ft.Row(_stat_chips(app, s, p, with_special=all_mode), wrap=True,
                       spacing=6, run_spacing=6))

    return card(
        ft.Column(body, spacing=12, tight=True),
        p,
    )


def build_review(app) -> ft.Control:
    p: Palette = app.palette
    t = date.today()
    week_start = t - timedelta(days=t.weekday())
    month_start = t.replace(day=1)

    if app.timeline_task_id != ALL:
        tasks = app.db.list_tasks(include_archived=True)
        if not any(x["id"] == app.timeline_task_id for x in tasks):
            app.timeline_task_id = ALL

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
