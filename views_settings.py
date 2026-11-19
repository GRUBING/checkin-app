"""设置页：任务管理、提醒、数据、主题。"""

from __future__ import annotations

import flet as ft

from db import STATUS_LABEL
from theme import Palette, status_text_color, tint
from widgets import card, chip, deadline_info, section_header

APP_VERSION = "v1.0.0"


def _task_meta(task: dict) -> str:
    parts = ["特殊任务" if task["type"] == "special" else "普通任务"]
    if task.get("reminder_time"):
        suffix = "每日" if (task.get("reminder_repeat") or "daily") == "daily" else "单次"
        parts.append(f"{suffix} {task['reminder_time']} 提醒" if task.get("reminder_enabled")
                     else f"提醒未开（{task['reminder_time']}）")
    if task["type"] == "special":
        info = deadline_info(task.get("deadline"))
        if info:
            parts.append(info[0])
    return " · ".join(parts)


def _task_row(app, task: dict) -> ft.Control:
    p: Palette = app.palette
    archived = bool(task["archived"])
    name_row = []
    if task["type"] == "special":
        name_row.append(ft.Icon(ft.Icons.STAR_ROUNDED, size=13, color=p.gold))
    name_row.append(
        ft.Text(task["name"], size=14, weight=ft.FontWeight.W_600,
                color=p.muted if archived else p.text, max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS, expand=True)
    )

    actions = [
        ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_size=17, icon_color=p.muted,
                      tooltip="编辑", on_click=lambda e, t=task: app.open_task_editor(t)),
        ft.TextButton(
            content=ft.Text("恢复" if archived else "归档", size=11, color=p.muted),
            tooltip="恢复到今日列表" if archived else "归档，不再出现在今日",
            on_click=lambda e, t=task: app.toggle_archive(t),
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8, vertical=4)),
        ),
        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=17, icon_color=p.muted,
                      tooltip="删除", on_click=lambda e, t=task: app.confirm_delete_task(t)),
    ]

    return ft.Row(
        [
            ft.Column(
                [
                    ft.Row(name_row, spacing=5, tight=True),
                    ft.Text(_task_meta(task), size=11, color=p.faint),
                ],
                spacing=2,
                tight=True,
                expand=True,
            ),
            ft.Row(actions, spacing=0, tight=True),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _action_row(icon: ft.IconData, title: str, subtitle: str, on_click,
                p: Palette, color: str | None = None) -> ft.Control:
    color = color or p.text
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, size=16, color=color),
                    width=34, height=34, border_radius=11, bgcolor=p.surface_soft,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    [
                        ft.Text(title, size=13, weight=ft.FontWeight.W_500, color=color),
                        ft.Text(subtitle, size=11, color=p.faint),
                    ],
                    spacing=1,
                    tight=True,
                    expand=True,
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=p.faint),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(vertical=9),
        on_click=on_click,
    )


def _task_management(app) -> ft.Control:
    p: Palette = app.palette
    tasks = app.db.list_tasks(include_archived=True)
    active = [t for t in tasks if not t["archived"]]
    archived = [t for t in tasks if t["archived"]]

    body: list[ft.Control] = [
        section_header("任务管理", p, f"{len(active)} 个进行中"),
    ]
    if active:
        for t in active:
            body.append(_task_row(app, t))
    else:
        body.append(ft.Text("还没有任务。", size=12, color=p.muted))

    body.append(
        ft.OutlinedButton("新建任务", icon=ft.Icons.ADD,
                          on_click=lambda e: app.open_task_editor(),
                          style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)))
    )

    if archived:
        body.append(ft.Container(height=2))
        body.append(ft.Text(f"已归档 · {len(archived)}", size=11, color=p.faint))
        for t in archived:
            body.append(_task_row(app, t))

    return card(ft.Column(body, spacing=10, tight=True), p)


def _reminder_card(app) -> ft.Control:
    p: Palette = app.palette
    enabled = app.db.get_setting("summary_enabled", "0") == "1"
    time_value = app.db.get_setting("summary_time", "21:00") or "21:00"

    time_box = ft.Container(
        content=ft.Row(
            [
                ft.Text(time_value, size=13, weight=ft.FontWeight.W_600,
                        color=p.text if enabled else p.muted),
                ft.Icon(ft.Icons.EXPAND_MORE, size=14, color=p.faint),
            ],
            spacing=2,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        width=82,
        height=36,
        alignment=ft.Alignment.CENTER,
        border_radius=10,
        border=ft.Border.all(1, p.line),
        bgcolor=p.surface_soft if enabled else None,
        on_click=lambda e: app.pick_summary_time(),
        tooltip="滑动选择时间",
    )

    return card(
        ft.Column(
            [
                section_header("提醒与通知", p),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("每日汇总提醒", size=13, weight=ft.FontWeight.W_500, color=p.text),
                                ft.Text("到点提醒今天还有多少任务没记录", size=11, color=p.faint),
                            ],
                            spacing=2,
                            tight=True,
                            expand=True,
                        ),
                        time_box,
                        ft.Switch(value=enabled, active_color=p.gold,
                                  inactive_thumb_color=p.surface,
                                  inactive_track_color=p.line,
                                  on_change=lambda e: app.toggle_summary(e.control.value)),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=14, color=p.gold),
                            ft.Text(
                                "App 打开时到点弹窗提醒并振动；错过时间的话，下次打开会补提醒。"
                                "彻底退出后的系统通知需要 Android 原生插件，当前版本尚未支持。",
                                size=10.5,
                                color=p.muted,
                                expand=True,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=tint(p.gold, 0.07),
                ),
            ],
            spacing=12,
            tight=True,
        ),
        p,
    )


def _appearance_card(app) -> ft.Control:
    p: Palette = app.palette
    mode = app.theme_mode
    return card(
        ft.Column(
            [
                section_header("外观", p),
                ft.Row(
                    [
                        ft.SegmentedButton(
                            segments=[
                                ft.Segment(value="light", label=ft.Text("浅色", no_wrap=True)),
                                ft.Segment(value="dark", label=ft.Text("深色", no_wrap=True)),
                                ft.Segment(value="system", label=ft.Text("跟随系统", no_wrap=True)),
                            ],
                            selected=[mode],
                            allow_empty_selection=False,
                            expand=True,
                            on_change=lambda e: app.change_theme(e.control.selected[0]),
                        )
                    ],
                    spacing=0,
                ),
            ],
            spacing=12,
            tight=True,
        ),
        p,
    )


def _data_card(app) -> ft.Control:
    p: Palette = app.palette
    return card(
        ft.Column(
            [
                section_header("数据", p, "本地优先 · 不上传云端"),
                _action_row(ft.Icons.NORTH_EAST, "导出 JSON", "把全部记录保存成一个文件",
                            lambda e: app.export_data(), p),
                _action_row(ft.Icons.DOWNLOAD, "导入 JSON", "用备份文件覆盖当前数据",
                            lambda e: app.import_data(), p),
                _action_row(ft.Icons.DELETE_OUTLINE, "清空全部数据", "任务与记录都会被删除",
                            lambda e: app.confirm_clear(), p, color=p.missed),
            ],
            spacing=4,
            tight=True,
        ),
        p,
    )


def build_settings(app) -> ft.Control:
    p: Palette = app.palette

    header = ft.Column(
        [
            ft.Text("设置", size=28, weight=ft.FontWeight.W_700, color=p.text),
            ft.Text("只属于你的本地记录。", size=12, color=p.muted),
        ],
        spacing=4,
        tight=True,
    )

    status_legend = ft.Row(
        [
            chip(f"{STATUS_LABEL['perfect']} / {STATUS_LABEL['smooth']} / "
                 f"{STATUS_LABEL['hard']} / {STATUS_LABEL['pain']}", p,
                 color=status_text_color(p, "smooth"),
                 bgcolor=tint(p.smooth, 0.10)),
            chip("补记带小圆点", p, color=p.gold, bgcolor=tint(p.gold, 0.10)),
        ],
        wrap=True,
        spacing=8,
        run_spacing=6,
    )

    return ft.Column(
        [
            header,
            _task_management(app),
            _reminder_card(app),
            _appearance_card(app),
            _data_card(app),
            card(
                ft.Column(
                    [
                        section_header("补卡规则", p),
                        ft.Text(
                            "在回顾页点击任意一天，就能为那天补记。补记会以「补」标记出现在历史里，"
                            "和当天的记录一样算数，只是多一个小圆点。未记录的日期只表示那天没有留下颜色，"
                            "不扣分、不羞辱、不中断任何东西。",
                            size=12,
                            color=p.muted,
                        ),
                        status_legend,
                    ],
                    spacing=12,
                    tight=True,
                ),
                p,
            ),
            ft.Column(
                [
                    ft.Text(f"打卡任务栏 {APP_VERSION} · 本地优先", size=11, color=p.faint,
                            text_align=ft.TextAlign.CENTER),
                    ft.Text("没有账号、没有云同步、没有排行榜。", size=10, color=p.faint,
                            text_align=ft.TextAlign.CENTER),
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=18,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
