"""打卡任务栏 · Flet 入口。

运行（桌面预览）：  python main.py
运行（浏览器预览）：python main.py --web
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import flet as ft

import views_review
import views_settings
import views_today
from db import (
    DB,
    STATUS_LABEL,
    effective_status,
    parse_date,
    weekday_cn,
)
from theme import STATUS_DESC, Palette, palette_for, status_color, status_text_color, tint
from widgets import card, chip, status_glyph, toast

MAX_WIDTH = 520


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.db = DB()
        self.tab = 0
        self.review_month = date.today().replace(day=1)
        self.timeline_task_id: int | str = "all"
        self.review_name_tasks: set[int] = set()
        self.clock_text: ft.Text | None = None
        self.theme_mode = self.db.get_setting("theme_mode", "light") or "light"
        self.palette = palette_for(self._is_dark())

        self.file_picker = ft.FilePicker()
        self.page.services.append(self.file_picker)
        self.haptic = ft.HapticFeedback()
        self.page.services.append(self.haptic)

        self._reminder_fired: set[str] = set()
        self._reminder_snoozed: dict[str, datetime] = {}
        self._reminder_showing = False

        page.title = "打卡任务栏"
        page.padding = 0
        page.bgcolor = self.palette.bg
        page.theme_mode = ft.ThemeMode.DARK if self._is_dark() else ft.ThemeMode.LIGHT
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        try:
            page.window.width = 430
            page.window.height = 880
            page.window.min_width = 360
            page.window.min_height = 640
        except Exception:
            pass

        self.content = ft.Container(expand=True)
        self.nav = ft.NavigationBar(
            selected_index=0,
            bgcolor=self.palette.surface,
            indicator_color=tint(self.palette.gold, 0.16),
            on_change=self._on_nav_change,
            destinations=self._destinations(),
        )
        shell = ft.Column([self.content, self.nav], spacing=0, expand=True)
        self.shell = ft.Container(shell, expand=True)
        page.add(
            ft.SafeArea(
                content=ft.Row(
                    [self.shell],
                    alignment=ft.MainAxisAlignment.CENTER,
                    expand=True,
                ),
                expand=True,
            )
        )
        page.on_resize = lambda e: self._sync_shell_width()

    def _shell_width(self) -> int | None:
        """屏幕宽度未知时返回 None，让容器铺满，避免窄屏被固定宽度撑出屏幕。"""
        width = self.page.width or 0
        if width <= 0:
            return None
        return int(min(width, MAX_WIDTH))

    def _content_padding(self) -> ft.Padding:
        width = self.page.width or 0
        narrow = bool(width and width < 390)
        side = 14 if narrow else 20
        top = 16 if narrow else 22
        return ft.Padding.only(left=side, right=side, top=top, bottom=8)

    def _dialog_width(self) -> int:
        """对话框内容宽度：随屏幕收窄，避免在手机上左右溢出。"""
        width = self.page.width or 380
        return max(220, min(320, int(width) - 96))

    def _sync_shell_width(self) -> None:
        width = self._shell_width()
        self.shell.width = width
        self.shell.expand = width is None
        self.content.padding = self._content_padding()
        self.page.update()

    # ------------------------------------------------------------ 基础渲染
    def _is_dark(self) -> bool:
        if self.theme_mode == "dark":
            return True
        if self.theme_mode == "system":
            return self.page.platform_brightness == ft.Brightness.DARK
        return False

    def _destinations(self) -> list[ft.NavigationBarDestination]:
        return [
            ft.NavigationBarDestination(icon=ft.Icons.TASK_ALT, label="今日"),
            ft.NavigationBarDestination(icon=ft.Icons.INSIGHTS, label="回顾"),
            ft.NavigationBarDestination(icon=ft.Icons.SETTINGS_OUTLINED, label="设置"),
        ]

    def render(self) -> None:
        p = self.palette
        self.page.bgcolor = p.bg
        self.page.theme_mode = ft.ThemeMode.DARK if self._is_dark() else ft.ThemeMode.LIGHT
        self.page.theme = self._material_theme(p)
        self.page.dark_theme = self._material_theme(p)
        if self.tab == 0:
            view = views_today.build_today(self)
        elif self.tab == 1:
            view = views_review.build_review(self)
        else:
            view = views_settings.build_settings(self)
        self.content.content = view
        self.content.padding = self._content_padding()
        self.nav.selected_index = self.tab
        self.nav.bgcolor = p.surface
        self.nav.indicator_color = tint(p.gold, 0.16)
        width = self._shell_width()
        self.shell.width = width
        self.shell.expand = width is None
        self.page.update()

    def _material_theme(self, p: Palette) -> ft.Theme:
        return ft.Theme(
            use_material3=True,
            color_scheme=ft.ColorScheme(
                primary=p.gold,
                on_primary="#FFFFFF" if not p.dark else "#241A05",
                primary_container=tint(p.gold, 0.24),
                on_primary_container=p.text,
                secondary_container=tint(p.gold, 0.22),
                on_secondary_container=p.text,
                surface=p.surface,
                on_surface=p.text,
                outline=p.line,
                outline_variant=p.line,
                error=p.missed,
            ),
            scaffold_bgcolor=p.bg,
        )

    def refresh(self) -> None:
        self.render()

    def _on_nav_change(self, e: ft.ControlEvent) -> None:
        self.tab = int(e.control.selected_index)
        self.render()

    def shift_month(self, delta: int) -> None:
        year, month = self.review_month.year, self.review_month.month + delta
        if month < 1:
            year, month = year - 1, 12
        elif month > 12:
            year, month = year + 1, 1
        self.review_month = date(year, month, 1)
        self.render()

    def set_timeline_task(self, task_id) -> None:
        self.timeline_task_id = "all" if task_id == "all" else int(task_id)
        self.render()

    def toggle_task_label(self, task_id: int) -> None:
        """柱状图纵轴的“任务1 / 任务2”点击后显示具体任务名称。"""
        if task_id in self.review_name_tasks:
            self.review_name_tasks.discard(task_id)
        else:
            self.review_name_tasks.add(task_id)
        self.render()

    # ------------------------------------------------------------ 打卡
    def open_checkin(self, task: dict, d: date) -> None:
        if d > date.today():
            toast(self.page, "未来日期还不能记录")
            return
        p: Palette = self.palette
        existing = self.db.get_checkin(task["id"], d)
        note_field = ft.TextField(
            value=(existing or {}).get("note") or "",
            hint_text="备注（可选）",
            multiline=True,
            min_lines=1,
            max_lines=2,
            text_size=12,
            border_radius=12,
            border_color=p.line,
            focused_border_color=p.gold,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        )

        def choose(status: str) -> None:
            try:
                self.db.upsert_checkin(task["id"], d, status, note_field.value or "")
            except ValueError as ex:
                toast(self.page, str(ex))
                return
            self.page.pop_dialog()
            if d < date.today():
                message = f"已补记 {d.month}月{d.day}日 · {STATUS_LABEL[status]}"
            elif existing:
                message = f"已更新为「{STATUS_LABEL[status]}」"
            else:
                message = "记下了"
            toast(self.page, message)
            self.render()

        def undo(e) -> None:
            self.db.delete_checkin(task["id"], d)
            self.page.pop_dialog()
            toast(self.page, "已撤销这条记录")
            self.render()

        def tile(status: str) -> ft.Control:
            color = status_color(p, status)
            selected = bool(existing and existing["status"] == status)
            return ft.Container(
                content=ft.Column(
                    [
                        status_glyph(status, p, 22, show_tooltip=False),
                        ft.Text(STATUS_LABEL[status], size=13,
                                weight=ft.FontWeight.W_600, max_lines=1,
                                color=status_text_color(p, status)),
                        ft.Text(STATUS_DESC[status], size=10, color=p.faint,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                text_align=ft.TextAlign.CENTER),
                    ],
                    spacing=3,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=6, vertical=10),
                border_radius=14,
                bgcolor=tint(color, 0.10 if selected else 0.04),
                border=ft.Border.all(1.6 if selected else 1, tint(color, 0.55 if selected else 0.25)),
                on_click=lambda e, s=status: choose(s),
                expand=True,
            )

        subtitle = f"{d.month}月{d.day}日 · 星期{weekday_cn(d)}"
        if d < date.today():
            subtitle += " · 补记"
        if existing:
            subtitle += f" · 当前：{STATUS_LABEL[existing['status']]}"

        body = ft.Column(
            [
                ft.Row([tile("perfect"), tile("smooth")], spacing=10),
                ft.Row([tile("hard"), tile("pain")], spacing=10),
                note_field,
            ],
            spacing=10,
            tight=True,
        )

        actions: list[ft.Control] = []
        if existing:
            actions.append(ft.TextButton("撤销记录", on_click=undo,
                                         style=ft.ButtonStyle(color=p.missed)))
        actions.append(ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()))

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=p.surface,
            title=ft.Column(
                [
                    ft.Text(task["name"], size=16, weight=ft.FontWeight.W_600, color=p.text),
                    ft.Text(subtitle, size=11, color=p.muted),
                ],
                spacing=2,
                tight=True,
            ),
            content=ft.Container(body, width=self._dialog_width()),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self.page.show_dialog(dialog)

    def open_day(self, d: date) -> None:
        p: Palette = self.palette
        if d > date.today():
            toast(self.page, "未来日期还不能记录")
            return
        tasks = self.db.tasks_for_date(d)
        checkins = self.db.day_checkins(d)

        rows: list[ft.Control] = []
        for t in tasks:
            c = checkins.get(t["id"])
            not_started = c is None and d < parse_date(t["created_at"])
            status = "pending" if not_started else effective_status(c, d)
            sub: list[str] = ["尚未开始 · 可补记" if not_started else STATUS_LABEL[status]]
            if c and c["is_backfill"]:
                sub.append("补记")
            if c and c.get("note"):
                sub.append(f"“{c['note']}”")
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            status_glyph(status, p, 22, backfill=bool(c and c["is_backfill"]),
                                          show_tooltip=False),
                            ft.Column(
                                [
                                    ft.Text(t["name"], size=13, weight=ft.FontWeight.W_500,
                                            color=p.text, max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Text(" · ".join(sub), size=10, color=p.muted),
                                ],
                                spacing=1,
                                tight=True,
                                expand=True,
                            ),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=15, color=p.faint),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=12,
                    bgcolor=p.surface_soft,
                    on_click=lambda e, task=t: (self.page.pop_dialog(), self.open_checkin(task, d)),
                )
            )
        if not rows:
            rows.append(ft.Text("那天还没有任务。", size=12, color=p.muted))

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=p.surface,
            title=ft.Column(
                [
                    ft.Text(f"{d.month}月{d.day}日", size=16, weight=ft.FontWeight.W_600, color=p.text),
                    ft.Text(f"星期{weekday_cn(d)} · 点击任务可补记或修改",
                            size=11, color=p.muted),
                ],
                spacing=2,
                tight=True,
            ),
            content=ft.Container(
                ft.Column(rows, spacing=6, tight=True,
                          scroll=ft.ScrollMode.AUTO, height=min(320, 54 * len(rows) + 8)),
                width=self._dialog_width(),
            ),
            actions=[ft.TextButton("关闭", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dialog)

    # ------------------------------------------------------------ 任务编辑
    def open_task_editor(self, task: dict | None = None) -> None:
        p: Palette = self.palette
        is_special = bool(task and task["type"] == "special")

        name_field = ft.TextField(
            label="任务名称", value=task["name"] if task else "", autofocus=True,
            text_size=14, border_radius=12, border_color=p.line, focused_border_color=p.gold,
        )
        type_sel = ft.SegmentedButton(
            segments=[
                ft.Segment(value="normal", label=ft.Text("普通任务", no_wrap=True)),
                ft.Segment(value="special", label=ft.Text("特殊任务", no_wrap=True)),
            ],
            selected=[task["type"] if task else "normal"],
            allow_empty_selection=False,
            expand=True,
            on_change=lambda e: on_type_change(),
        )
        deadline_field = ft.TextField(
            label="截止日期（可选）", hint_text="YYYY-MM-DD", text_size=13, border_radius=12,
            border_color=p.line, focused_border_color=p.gold,
            value=(task.get("deadline") or "") if task else "", visible=is_special,
        )
        reminder_state = {"time": (task.get("reminder_time") or "") if task else ""}
        reminder_value = ft.Text(
            reminder_state["time"] or "未设置",
            size=13,
            weight=ft.FontWeight.W_600,
            color=p.text if reminder_state["time"] else p.faint,
        )
        reminder_box = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.NOTIFICATIONS_NONE, size=16, color=p.muted),
                    ft.Text("提醒时间", size=12, color=p.muted),
                    ft.Container(expand=True),
                    reminder_value,
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=p.faint),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            border_radius=12,
            border=ft.Border.all(1, p.line),
            bgcolor=p.surface_soft,
            on_click=lambda e: pick_reminder_time(),
        )

        def pick_reminder_time() -> None:
            def apply(value: str) -> None:
                reminder_state["time"] = value
                reminder_value.value = value or "未设置"
                reminder_value.color = p.text if value else p.faint
                self.page.update()

            self.pick_time(
                reminder_state["time"] or "21:00",
                "选择提醒时间",
                apply,
                allow_clear=bool(reminder_state["time"]),
            )

        repeat_dd = ft.Dropdown(
            label="重复",
            value=(task.get("reminder_repeat") or "daily") if task else "daily",
            options=[ft.DropdownOption(key="daily", text="每日"),
                     ft.DropdownOption(key="once", text="仅一次")],
            text_size=13,
            border_radius=12,
            border_color=p.line,
            focused_border_color=p.gold,
        )
        reminder_switch = ft.Switch(
            label="开启提醒",
            value=bool(task.get("reminder_enabled")) if task else False,
            active_color=p.gold,
        )

        def on_type_change() -> None:
            special = bool(type_sel.selected and type_sel.selected[0] == "special")
            deadline_field.visible = special
            self.page.update()

        def save(e) -> None:
            try:
                name = (name_field.value or "").strip()
                if not name:
                    raise ValueError("请填写任务名称")
                type_ = (type_sel.selected or ["normal"])[0]
                deadline = (deadline_field.value or "").strip() or None
                if type_ != "special":
                    deadline = None
                if deadline:
                    try:
                        parse_date(deadline)
                    except ValueError:
                        raise ValueError("截止日期格式应为 YYYY-MM-DD") from None
                rtime = reminder_state["time"] or None
                if reminder_switch.value and not rtime:
                    raise ValueError("开启提醒时需要先选择提醒时间")

                if task:
                    self.db.update_task(task["id"], name=name, type=type_, deadline=deadline)
                    self.db.set_reminder(task["id"], rtime, repeat_dd.value or "daily",
                                         reminder_switch.value)
                else:
                    self.db.add_task(name, type_, deadline=deadline, reminder_time=rtime,
                                     repeat_rule=repeat_dd.value or "daily",
                                     reminder_enabled=bool(reminder_switch.value))
            except ValueError as ex:
                toast(self.page, str(ex))
                return
            self.page.pop_dialog()
            toast(self.page, "已保存")
            self.render()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=p.surface,
            title=ft.Text("编辑任务" if task else "新建任务", size=16,
                          weight=ft.FontWeight.W_600, color=p.text),
            content=ft.Container(
                ft.Column(
                    [
                        name_field,
                        ft.Row([type_sel], spacing=0),
                        deadline_field,
                        reminder_box,
                        repeat_dd,
                        reminder_switch,
                    ],
                    spacing=12,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=self._dialog_width(),
                height=max(240, min(400, int((self.page.height or 760) * 0.55))),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("保存", on_click=save),
            ],
        )
        self.page.show_dialog(dialog)

    def toggle_archive(self, task: dict) -> None:
        self.db.set_archived(task["id"], not bool(task["archived"]))
        toast(self.page, "已恢复" if task["archived"] else "已归档")
        self.render()

    def confirm_delete_task(self, task: dict) -> None:
        p = self.palette

        def do_delete(e) -> None:
            self.db.delete_task(task["id"])
            self.page.pop_dialog()
            toast(self.page, "已删除")
            self.render()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=p.surface,
                title=ft.Text("删除任务？", size=16, weight=ft.FontWeight.W_600, color=p.text),
                content=ft.Text(f"「{task['name']}」以及它的全部记录都会被删除，无法恢复。",
                                size=12, color=p.muted),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                    ft.TextButton("删除", on_click=do_delete,
                                  style=ft.ButtonStyle(color=p.missed)),
                ],
            )
        )

    # ------------------------------------------------------------ 设置
    def change_theme(self, mode: str) -> None:
        if mode not in ("light", "dark", "system"):
            return
        self.theme_mode = mode
        self.db.set_setting("theme_mode", mode)
        self.palette = palette_for(self._is_dark())
        self.render()

    def toggle_summary(self, enabled: bool) -> None:
        self.db.set_setting("summary_enabled", "1" if enabled else "0")
        toast(self.page, "已开启每日汇总提醒" if enabled else "已关闭每日汇总提醒")
        self.render()

    def confirm_clear(self) -> None:
        p = self.palette

        def do_clear(e) -> None:
            self.db.clear_all()
            self.page.pop_dialog()
            self.timeline_task_id = "all"
            toast(self.page, "全部数据已清空")
            self.render()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=p.surface,
                title=ft.Text("清空全部数据？", size=16, weight=ft.FontWeight.W_600, color=p.text),
                content=ft.Text("任务、打卡记录和设置都会被删除，且无法恢复。建议先导出备份。",
                                size=12, color=p.muted),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                    ft.TextButton("清空", on_click=do_clear,
                                  style=ft.ButtonStyle(color=p.missed)),
                ],
            )
        )

    # ------------------------------------------------------------ 导入导出
    def export_data(self, e=None) -> None:
        self.page.run_task(self._export_task)

    async def _export_task(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"checkin_{stamp}.json"
        try:
            path = await self.file_picker.save_file(file_name=filename,
                                                    allowed_extensions=["json"])
            if not path:
                return
            self.db.export_to_file(path)
            toast(self.page, f"已导出到 {path}")
        except Exception:
            fallback = self.db.export_to_file(self.db.path.parent / "exports" / filename)
            self.show_info("已导出到应用目录",
                           f"系统文件选择不可用，文件保存在：\n{fallback}")

    def import_data(self, e=None) -> None:
        self.page.run_task(self._import_task)

    async def _import_task(self) -> None:
        try:
            files = await self.file_picker.pick_files(allowed_extensions=["json"],
                                                      allow_multiple=False)
        except Exception:
            self.show_info("无法打开文件选择", "当前环境不支持系统文件选择。可以把 JSON 备份放到应用目录后重试。")
            return
        if not files:
            return
        picked = files[0]
        try:
            data = json.loads(Path(picked.path).read_text(encoding="utf-8"))
        except Exception as ex:
            self.show_info("读取失败", f"这个文件不是有效的 JSON：{ex}")
            return
        p = self.palette

        def do_import(e) -> None:
            try:
                self.db.import_data(data, replace=True)
            except ValueError as ex:
                self.page.pop_dialog()
                toast(self.page, str(ex))
                return
            self.page.pop_dialog()
            self.timeline_task_id = "all"
            toast(self.page, "已导入备份")
            self.render()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=p.surface,
                title=ft.Text("导入备份？", size=16, weight=ft.FontWeight.W_600, color=p.text),
                content=ft.Text(
                    f"将用「{picked.name}」覆盖当前全部任务和记录。建议先导出当前数据。",
                    size=12, color=p.muted),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton("覆盖导入", on_click=do_import),
                ],
            )
        )

    def show_info(self, title: str, message: str) -> None:
        p = self.palette
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=p.surface,
                title=ft.Text(title, size=16, weight=ft.FontWeight.W_600, color=p.text),
                content=ft.Text(message, size=12, color=p.muted, selectable=True),
                actions=[ft.TextButton("好的", on_click=lambda e: self.page.pop_dialog())],
            )
        )

    # ------------------------------------------------------------ 时间选择
    def pick_time(self, initial: str, title: str, on_confirm, allow_clear: bool = False) -> None:
        """滑动滚轮选择时间，替代手动输入 HH:MM。"""
        p = self.palette
        try:
            hh, mm = (int(x) for x in initial.split(":")[:2])
            hh, mm = hh % 24, mm % 60
        except Exception:
            hh, mm = 21, 0

        state = {"h": hh, "m": mm}
        hour_picker = ft.CupertinoPicker(
            controls=[ft.Text(f"{h:02d}", size=20, color=p.text) for h in range(24)],
            selected_index=hh,
            item_extent=36,
            width=68,
            height=168,
            use_magnifier=True,
            looping=True,
            default_selection_overlay_bgcolor=tint(p.gold, 0.14),
            on_change=lambda e: state.__setitem__("h", int(e.control.selected_index)),
        )
        minute_picker = ft.CupertinoPicker(
            controls=[ft.Text(f"{m:02d}", size=20, color=p.text) for m in range(60)],
            selected_index=mm,
            item_extent=36,
            width=68,
            height=168,
            use_magnifier=True,
            looping=True,
            default_selection_overlay_bgcolor=tint(p.gold, 0.14),
            on_change=lambda e: state.__setitem__("m", int(e.control.selected_index)),
        )

        def confirm(e) -> None:
            self.page.pop_dialog()
            on_confirm(f"{state['h']:02d}:{state['m']:02d}")

        def clear(e) -> None:
            self.page.pop_dialog()
            on_confirm("")

        actions: list[ft.Control] = []
        if allow_clear:
            actions.append(ft.TextButton("清除", on_click=clear))
        actions.append(ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()))
        actions.append(ft.FilledButton("确定", on_click=confirm))

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=p.surface,
                title=ft.Text(title, size=16, weight=ft.FontWeight.W_600, color=p.text),
                content=ft.Container(
                    ft.Row(
                        [
                            hour_picker,
                            ft.Text("时", size=12, color=p.muted),
                            minute_picker,
                            ft.Text("分", size=12, color=p.muted),
                        ],
                        spacing=4,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    width=self._dialog_width(),
                    height=184,
                    alignment=ft.Alignment.CENTER,
                ),
                actions=actions,
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    def pick_summary_time(self) -> None:
        current = self.db.get_setting("summary_time", "21:00") or "21:00"

        def apply(value: str) -> None:
            if not value:
                return
            self.db.set_setting("summary_time", value)
            toast(self.page, f"每日汇总时间已设为 {value}")
            self.render()

        self.pick_time(current, "每日汇总时间", apply)

    # ------------------------------------------------------------ 到点提醒
    def _reminder_key(self, kind: str, ident: str = "") -> str:
        return f"{kind}:{ident}:{date.today().isoformat()}"

    def _is_due(self, key: str, scheduled: datetime, now: datetime) -> bool:
        if key in self._reminder_fired:
            return False
        snooze_until = self._reminder_snoozed.get(key)
        if snooze_until is not None:
            return now >= snooze_until
        # 当天错过整分钟（切后台、刚打开 App）时，打开后补一次提醒
        return now >= scheduled

    def _dialog_busy(self) -> bool:
        if self._reminder_showing:
            return True
        try:
            return bool(self.page._dialogs.controls)
        except Exception:
            return False

    def _due_task_reminders(self, now: datetime) -> list[tuple[dict, str]]:
        today = date.today()
        checkins = self.db.day_checkins(today)
        due: list[tuple[dict, str]] = []
        for t in self.db.list_tasks():
            rtime = t.get("reminder_time")
            if not t.get("reminder_enabled") or not rtime:
                continue
            try:
                hh, mm = (int(x) for x in str(rtime).split(":")[:2])
                scheduled = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            except Exception:
                continue
            if t["id"] in checkins:
                continue
            key = f"task:{t['id']}:{today.isoformat()}:{rtime}"
            if self._is_due(key, scheduled, now):
                due.append((t, key))
        return due

    def _due_summary(self, now: datetime) -> list[dict] | None:
        if str(self.db.get_setting("summary_enabled", "0")) != "1":
            return None
        rtime = self.db.get_setting("summary_time", "21:00") or "21:00"
        try:
            hh, mm = (int(x) for x in str(rtime).split(":")[:2])
            scheduled = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except Exception:
            return None
        key = self._reminder_key("summary", str(rtime))
        if not self._is_due(key, scheduled, now):
            return None
        checkins = self.db.day_checkins(date.today())
        pending = [t for t in self.db.list_tasks() if t["id"] not in checkins]
        self._reminder_fired.add(key)
        return pending

    def _disable_once_reminders(self, due: list[tuple[dict, str]]) -> None:
        for t, _ in due:
            if (t.get("reminder_repeat") or "daily") == "once" and t.get("reminder_enabled"):
                self.db.set_reminder(t["id"], t.get("reminder_time"), "once", False)

    async def _show_task_reminder(self, due: list[tuple[dict, str]], now: datetime) -> None:
        self._reminder_showing = True
        for _, key in due:
            self._reminder_fired.add(key)
            self._reminder_snoozed.pop(key, None)
        try:
            await self.haptic.vibrate()
        except Exception:
            pass

        p = self.palette
        rows: list[ft.Control] = []
        for t, _ in due[:4]:
            rows.append(
                ft.Row(
                    [
                        ft.Container(width=5, height=5, border_radius=3,
                                     bgcolor=tint(p.gold, 0.9)),
                        ft.Text(t["name"], size=13, color=p.text, max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                        ft.Text(t.get("reminder_time") or "", size=11, color=p.muted),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        if len(due) > 4:
            rows.append(ft.Text(f"还有 {len(due) - 4} 个任务…", size=11, color=p.muted))

        def snooze(e) -> None:
            for _, key in due:
                self._reminder_fired.discard(key)
                self._reminder_snoozed[key] = now + timedelta(minutes=10)
            self._reminder_showing = False
            self.page.pop_dialog()
            toast(self.page, "10 分钟后再提醒你")

        def dismiss(e) -> None:
            self._reminder_showing = False
            self.page.pop_dialog()
            self._disable_once_reminders(due)

        def go(e) -> None:
            self._reminder_showing = False
            self.page.pop_dialog()
            self._disable_once_reminders(due)
            self.open_checkin(due[0][0], date.today())

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=p.surface,
                title=ft.Column(
                    [
                        ft.Text("该打卡了", size=17, weight=ft.FontWeight.W_600, color=p.text),
                        ft.Text(f"{now.strftime('%H:%M')} · 今天还没有记录", size=11, color=p.muted),
                    ],
                    spacing=2,
                    tight=True,
                ),
                content=ft.Container(
                    ft.Column(
                        rows + [ft.Text("记下之后，今天就不会再提醒。", size=10, color=p.faint)],
                        spacing=8,
                        tight=True,
                    ),
                    width=self._dialog_width(),
                ),
                actions=[
                    ft.TextButton("稍后提醒", on_click=snooze),
                    ft.TextButton("知道了", on_click=dismiss),
                    ft.FilledButton("去打卡", on_click=go),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def _show_summary_reminder(self, pending: list[dict], now: datetime) -> None:
        if not pending:
            return
        self._reminder_showing = True
        try:
            await self.haptic.vibrate()
        except Exception:
            pass

        p = self.palette
        key = self._reminder_key(
            "summary", str(self.db.get_setting("summary_time", "21:00") or "21:00")
        )

        def snooze(e) -> None:
            self._reminder_fired.discard(key)
            self._reminder_snoozed[key] = now + timedelta(minutes=10)
            self._reminder_showing = False
            self.page.pop_dialog()
            toast(self.page, "10 分钟后再提醒你")

        def dismiss(e) -> None:
            self._reminder_showing = False
            self.page.pop_dialog()

        def go(e) -> None:
            self._reminder_showing = False
            self.page.pop_dialog()
            self.tab = 0
            self.render()

        names = "、".join(t["name"] for t in pending[:4])
        if len(pending) > 4:
            names += f" 等 {len(pending)} 个任务"

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=p.surface,
                title=ft.Column(
                    [
                        ft.Text("今天还没收尾", size=17, weight=ft.FontWeight.W_600, color=p.text),
                        ft.Text(f"{now.strftime('%H:%M')} · 每日汇总", size=11, color=p.muted),
                    ],
                    spacing=2,
                    tight=True,
                ),
                content=ft.Container(
                    ft.Column(
                        [
                            ft.Text(f"还有 {len(pending)} 个任务没有记录：", size=12, color=p.text),
                            ft.Text(names, size=12, color=p.muted),
                            ft.Text("现在补上，或者明早在回顾里补记。", size=10, color=p.faint),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                    width=self._dialog_width(),
                ),
                actions=[
                    ft.TextButton("稍后提醒", on_click=snooze),
                    ft.TextButton("知道了", on_click=dismiss),
                    ft.FilledButton("去记录", on_click=go),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def reminder_loop(self) -> None:
        """App 运行期间每 15 秒检查一次到点提醒。"""
        while True:
            await asyncio.sleep(15)
            try:
                if self._dialog_busy():
                    continue
                now = datetime.now()
                due = self._due_task_reminders(now)
                if due:
                    await self._show_task_reminder(due, now)
                    continue
                pending = self._due_summary(now)
                if pending is not None:
                    await self._show_summary_reminder(pending, now)
            except Exception:
                pass

    # ------------------------------------------------------------ 时钟
    async def clock_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                if self.tab == 0 and self.clock_text is not None:
                    self.clock_text.value = datetime.now().strftime("%H:%M")
                    self.page.update()
            except Exception:
                pass


def main(page: ft.Page) -> None:
    app = App(page)
    page.run_task(app.clock_loop)
    page.run_task(app.reminder_loop)
    app.render()


if __name__ == "__main__":
    if "--web" in sys.argv:
        ft.run(main, view=ft.AppView.WEB_BROWSER)
    else:
        ft.run(main)
