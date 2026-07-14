"""
Грошове забезпечення патронатного вихователя — мобільна версія (Kivy / Android).
Світла тема з червоним акцентом. Логіка розрахунку ідентична десктопній програмі.
"""

import os
import json
import calendar
from datetime import date, datetime, timedelta

from kivy.app import App
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.popup import Popup
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, RoundedRectangle, Line

ДЕФОЛТ_СТАВКА = 8000.0
ДЕФОЛТ_ПМ_ДО6 = 2563.0
ДЕФОЛТ_ПМ_ВІД6 = 3028.0

# ---- палітра (світла тема) ----
BG     = (0.957, 0.945, 0.925, 1)   # #f4f1ec
CARD   = (1, 1, 1, 1)
BORDER = (0.910, 0.890, 0.855, 1)   # #e8e3da
RED    = (0.847, 0.275, 0.247, 1)   # #D8463F
TEXT   = (0.169, 0.153, 0.141, 1)   # #2b2724
SUB    = (0.420, 0.392, 0.361, 1)   # #6b645c
MUTED  = (0.604, 0.576, 0.541, 1)   # #9a938a
RED_BG = (0.988, 0.937, 0.933, 1)   # світло-червоний фон мітки


# =========================
# Формули розрахунку (ідентичні десктопній версії)
# =========================
def child_days_in_month(start, end, calc_year, calc_month):
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    first = date(calc_year, calc_month, 1)
    last  = date(calc_year, calc_month, days_in_month)
    if start > last:
        return 0
    if end is not None and end < first:
        return 0
    day_from = start.day if (start.year == calc_year and start.month == calc_month) else 1
    if end is not None and end.year == calc_year and end.month == calc_month:
        day_to = end.day
    else:
        day_to = days_in_month
    return max(0, day_to - day_from + 1)


def sixth_birthday(birth):
    try:
        return date(birth.year + 6, birth.month, birth.day)
    except ValueError:
        return date(birth.year + 6, birth.month, 28)


def child_days_split_by_age(start, end, birth, calc_year, calc_month):
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    first = date(calc_year, calc_month, 1)
    last  = date(calc_year, calc_month, days_in_month)
    if start > last:
        return 0, 0
    if end is not None and end < first:
        return 0, 0
    d_from = max(start, first)
    d_to   = min(end, last) if end is not None else last
    if d_from > d_to:
        return 0, 0
    total = (d_to - d_from).days + 1
    sixth = sixth_birthday(birth)
    if sixth <= d_from:
        return 0, total
    if sixth > d_to:
        return total, 0
    days_under = (sixth - d_from).days
    return days_under, total - days_under


def calc_child_support(pm_do6, pm_vid6, start, end, birth, invalid, calc_year, calc_month):
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    d_under, d_over = child_days_split_by_age(start, end, birth, calc_year, calc_month)
    multiplier = 3.5 if invalid else 2.5
    return (pm_do6 * multiplier * d_under + pm_vid6 * multiplier * d_over) / days_in_month


def is_under1(birth, calc_year, calc_month):
    month_start = date(calc_year, calc_month, 1)
    try:
        first_bday = date(birth.year + 1, birth.month, birth.day)
    except ValueError:
        first_bday = date(birth.year + 1, birth.month, 28)
    return first_bday > month_start


def calc_total_child_days(children, calc_year, calc_month):
    return sum(child_days_in_month(c["start"], c["end"], calc_year, calc_month) for c in children)


def calc_bonus_segments(base_3, children, calc_year, calc_month):
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    tally = {}
    for day in range(1, days_in_month + 1):
        d = date(calc_year, calc_month, day)
        n = sum(1 for c in children
                if c["start"] <= d and (c["end"] is None or c["end"] >= d))
        tally[n] = tally.get(n, 0) + 1
    segments = []
    total = 0.0
    for count in sorted(tally.keys(), reverse=True):
        if count == 0:
            continue
        days = tally[count]
        pct = count * 10
        amount = base_3 * (pct / 100) * days / days_in_month
        total += amount
        segments.append({"count": count, "pct": pct, "days": days, "amount": amount})
    return segments, total


def calc_salary_breakdown(stavka, total_bonus_pct, children, calc_year, calc_month):
    """Грошове забезпечення — завжди базові 3 ставки (+ надбавка).
    Пільговий 7-денний термін і зниження до 1 ставки (коли немає дітей) НЕ застосовуються."""
    normal_full = stavka * 3 * (1 + total_bonus_pct / 100)
    return {"normal": normal_full, "low": 0.0, "note": ""}


def build_result(stavka, pm_do6, pm_vid6, children, calc_year, calc_month, month_str):
    """Повертає (текст_результату, разом_грн)."""
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    base_3 = stavka * 3
    sal = calc_salary_breakdown(stavka, 0, children, calc_year, calc_month)
    base_salary = sal["normal"] + sal["low"]
    bonus_segments, bonus_amount = calc_bonus_segments(base_3, children, calc_year, calc_month)
    caregiver_zp = base_salary + bonus_amount

    child_lines   = []
    total_support = 0.0
    for c in children:
        amount = calc_child_support(pm_do6, pm_vid6, c["start"], c["end"], c["birth"],
                                    c["invalid"], calc_year, calc_month)
        days   = child_days_in_month(c["start"], c["end"], calc_year, calc_month)
        d_under, d_over = child_days_split_by_age(c["start"], c["end"], c["birth"],
                                                  calc_year, calc_month)
        total_support += amount
        if days == days_in_month:
            note = "повний місяць"
        elif days > 0:
            note = f"{days} з {days_in_month} дн."
        else:
            note = "не в розрахунковому місяці"
        flags = []
        if is_under1(c["birth"], calc_year, calc_month):  flags.append("<1р")
        if c["invalid"]: flags.append("інв")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        mult = "3.5 ПМ" if c["invalid"] else "2.5 ПМ"
        if d_under > 0 and d_over > 0:
            age_note = f"{mult}: до 6р {d_under} дн. + 6-18р {d_over} дн."
        elif d_under > 0:
            age_note = f"{mult}, до 6 років"
        elif d_over > 0:
            age_note = f"{mult}, 6-18 років"
        else:
            age_note = mult
        child_lines.append(f"  {c['name']}{flag_str}  ({note}, {age_note}):  {amount:.2f} грн")

    total = caregiver_zp + total_support

    lines = []
    if sal["note"]:
        if sal["low"] > 0 and sal["normal"] > 0:
            lines.append("Грошове забезпечення вихователя:")
            lines.append(f"  {sal['note']}")
            lines.append(f"  Звичайна частина (3 ставки):  {sal['normal']:.2f} грн")
            lines.append(f"  1 ставка:  {sal['low']:.2f} грн")
        else:
            lines.append(f"Базове грошове забезпечення:  {base_salary:.2f} грн")
            lines.append(f"  ({sal['note']})")
    else:
        lines.append(f"Базове грошове забезпечення (3 ставки):  {base_3:.2f} грн")
    if bonus_amount > 0:
        lines.append("  Надбавка за дітей (по днях):")
        for s in bonus_segments:
            lines.append(f"    +{s['pct']}% ({s['count']} дит. x {s['days']} дн.):  {s['amount']:.2f} грн")
        if len(bonus_segments) > 1:
            lines.append(f"    Разом надбавка:  {bonus_amount:.2f} грн")
    lines.append(f"  Разом грошове забезпечення:  {caregiver_zp:.2f} грн")
    zp_block = "\n".join(lines)

    text = (
        f"Розрахунковий місяць: {month_str}  ({days_in_month} дн.)\n"
        f"Ставка: {stavka:.2f} грн\n"
        f"ПМ до 6р: {pm_do6:.2f} грн | ПМ 6-18р: {pm_vid6:.2f} грн\n\n"
        f"{zp_block}\n\n"
        f"Соціальна допомога на дітей (2.5 ПМ, для дітей-інвалідів — 3.5 ПМ):\n"
        + ("\n".join(child_lines) if child_lines else "  — дітей немає")
        + f"\n  Разом соціальна допомога:  {total_support:.2f} грн\n\n"
        f"РАЗОМ: {total:.2f} грн"
    )
    return text, total


# =========================
# Стилізовані віджети
# =========================
def _round_bg(widget, color, radius, border=None):
    with widget.canvas.before:
        widget._bgc = Color(*color)
        widget._bgr = RoundedRectangle(radius=[radius])
        if border:
            widget._brc = Color(*border)
            widget._brl = Line(width=1.1)

    def upd(*a):
        widget._bgr.pos = widget.pos
        widget._bgr.size = widget.size
        if border:
            x, y = widget.pos
            w, h = widget.size
            widget._brl.rounded_rectangle = (x, y, w, h, radius)
    widget.bind(pos=upd, size=upd)


class Card(BoxLayout):
    def __init__(self, radius=dp(12), bg=CARD, border=BORDER, **kw):
        kw.setdefault("orientation", "vertical")
        super().__init__(**kw)
        self.size_hint_y = None
        _round_bg(self, bg, radius, border)


class Pill(ButtonBehavior, Label):
    def __init__(self, bg=RED, fg=(1, 1, 1, 1), radius=dp(12), border=None, **kw):
        super().__init__(**kw)
        self.color = fg
        _round_bg(self, bg, radius, border)


def lbl(text, color=TEXT, size=14, bold=False, halign="left", **kw):
    w = Label(text=text, color=color, font_size=sp(size), bold=bold,
              halign=halign, valign="middle", **kw)
    w.bind(size=lambda *a: setattr(w, "text_size", (w.width, None)))
    return w


def make_input(value, **kw):
    ti = TextInput(text=str(value), multiline=False, size_hint_y=None, height=dp(40),
                   background_normal="", background_active="",
                   background_color=CARD, foreground_color=TEXT, cursor_color=RED,
                   padding=[dp(10), dp(9)], font_size=sp(14), **kw)
    return ti


def toast(title, text):
    box = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))
    box.add_widget(lbl(text, color=TEXT, halign="center"))
    b = Pill(text="Гаразд", bg=RED, size_hint_y=None, height=dp(44), font_size=sp(15))
    box.add_widget(b)
    p = Popup(title=title, content=box, size_hint=(0.85, None), height=dp(210),
              title_color=TEXT, separator_color=RED, background_color=(1, 1, 1, 1))
    b.bind(on_release=p.dismiss)
    p.open()


# =========================
# Діалог дитини
# =========================
class ChildDialog(Popup):
    def __init__(self, on_save, child=None, **kw):
        super().__init__(**kw)
        self.on_save = on_save
        is_edit = child is not None
        self.title = "Редагувати дитину" if is_edit else "Додати дитину"
        self.title_color = TEXT
        self.separator_color = RED
        self.background_color = (1, 1, 1, 1)
        self.size_hint = (0.95, 0.9)

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))

        def field(label_text, value):
            grid.add_widget(lbl(label_text, color=SUB, size=13, size_hint_y=None, height=dp(22)))
            ti = make_input(value)
            grid.add_widget(ti)
            return ti

        self.name_in  = field("Ім'я / ПІБ:", child["name"] if is_edit else "")
        self.birth_in = field("Дата народження (ДД.ММ.РРРР):",
                              child["birth"].strftime("%d.%m.%Y") if is_edit else "")
        self.start_in = field("Дата прийняття (ДД.ММ.РРРР):",
                              child["start"].strftime("%d.%m.%Y") if is_edit
                              else date.today().strftime("%d.%m.%Y"))
        self.end_in   = field("Дата вибуття (порожнє = ще не вибув):",
                              child["end"].strftime("%d.%m.%Y") if (is_edit and child["end"]) else "")

        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.invalid_cb = CheckBox(active=child["invalid"] if is_edit else False,
                                   size_hint_x=None, width=dp(40), color=RED)
        row.add_widget(self.invalid_cb)
        row.add_widget(lbl("Інвалідність (соц. допомога 3.5 ПМ)", color=TEXT, size=13))
        grid.add_widget(row)
        grid.add_widget(lbl("«До 1 року» — автоматично за датою народження.\n"
                            "Надбавка: +10% за кожну дитину.",
                            color=MUTED, size=11, size_hint_y=None, height=dp(40)))

        scroll = ScrollView()
        scroll.add_widget(grid)
        root.add_widget(scroll)

        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        save_btn = Pill(text="Зберегти" if is_edit else "Додати", bg=RED, font_size=sp(15))
        cancel_btn = Pill(text="Скасувати", bg=CARD, fg=SUB, border=BORDER, font_size=sp(15))
        save_btn.bind(on_release=self._save)
        cancel_btn.bind(on_release=self.dismiss)
        btns.add_widget(save_btn)
        btns.add_widget(cancel_btn)
        root.add_widget(btns)
        self.content = root

    def _save(self, *_):
        name = self.name_in.text.strip()
        if not name:
            toast("Помилка", "Введіть ім'я дитини.")
            return
        try:
            birth = datetime.strptime(self.birth_in.text.strip(), "%d.%m.%Y").date()
        except ValueError:
            toast("Помилка", "Дата народження у форматі ДД.ММ.РРРР")
            return
        try:
            start = datetime.strptime(self.start_in.text.strip(), "%d.%m.%Y").date()
        except ValueError:
            toast("Помилка", "Дата прийняття у форматі ДД.ММ.РРРР")
            return
        if start < birth:
            toast("Помилка", "Прийняття не може бути раніше народження.")
            return
        end = None
        raw_end = self.end_in.text.strip()
        if raw_end:
            try:
                end = datetime.strptime(raw_end, "%d.%m.%Y").date()
            except ValueError:
                toast("Помилка", "Дата вибуття у форматі ДД.ММ.РРРР")
                return
            if end < start:
                toast("Помилка", "Вибуття не може бути раніше прийняття.")
                return
        self.on_save({
            "name": name, "birth": birth, "start": start, "end": end,
            "invalid": self.invalid_cb.active,
        })
        self.dismiss()


# =========================
# Головний застосунок
# =========================
class ZPApp(App):
    title = "Грошове забезпечення патронатного вихователя"

    def build(self):
        Window.clearcolor = BG
        Window.softinput_mode = "below_target"
        self.settings_path = os.path.join(self.user_data_dir, "settings.json")
        self.children_path = os.path.join(self.user_data_dir, "children.json")
        self.children_list = self.load_children()
        stavka, pm_do6, pm_vid6 = self.load_settings()

        root = ScrollView()
        col = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12),
                        size_hint_y=None)
        col.bind(minimum_height=col.setter("height"))

        # ---- Хедер ----
        header = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        icon = Pill(text="₴", bg=RED, font_size=sp(22), bold=True,
                    size_hint_x=None, width=dp(44))
        header.add_widget(icon)
        htitle = BoxLayout(orientation="vertical")
        htitle.add_widget(lbl("Грошове забезпечення", color=TEXT, size=15, bold=True))
        htitle.add_widget(lbl("патронатного вихователя", color=MUTED, size=12))
        header.add_widget(htitle)
        col.add_widget(header)

        # ---- Налаштування ----
        sett = Card(padding=[dp(12), dp(12)], spacing=dp(4))
        sett.add_widget(lbl("НАЛАШТУВАННЯ", color=MUTED, size=11, size_hint_y=None, height=dp(20)))

        def setting_row(label_text, value):
            r = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            r.add_widget(lbl(label_text, color=SUB, size=13))
            ti = make_input(value, size_hint_x=None, width=dp(110), halign="right")
            r.add_widget(ti)
            sett.add_widget(r)
            return ti

        self.stavka_in  = setting_row("Ставка (грн)", stavka)
        self.pm_do6_in  = setting_row("ПМ до 6 років", pm_do6)
        self.pm_vid6_in = setting_row("ПМ 6–18 років", pm_vid6)
        save_set = Pill(text="Зберегти", bg=CARD, fg=RED, border=BORDER,
                        size_hint_y=None, height=dp(38), font_size=sp(13))
        save_set.bind(on_release=self.save_settings_clicked)
        sett.add_widget(save_set)
        sett.height = dp(20) + dp(44) * 3 + dp(38) + dp(30)
        col.add_widget(sett)

        # ---- Місяць + кількість ----
        mrow = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(10))
        mcard = Card(padding=[dp(12), dp(9)], spacing=dp(2))
        mcard.add_widget(lbl("Місяць (ММ.РРРР)", color=MUTED, size=11, size_hint_y=None, height=dp(18)))
        self.month_in = make_input(date.today().strftime("%m.%Y"))
        mcard.add_widget(self.month_in)
        mcard.height = dp(64)
        mrow.add_widget(mcard)
        ccard = Card(padding=[dp(12), dp(9)], spacing=dp(2), size_hint_x=None, width=dp(90))
        ccard.add_widget(lbl("Дітей", color=MUTED, size=11, size_hint_y=None, height=dp(18)))
        self.count_lbl = lbl("0", color=TEXT, size=18, bold=True)
        ccard.add_widget(self.count_lbl)
        ccard.height = dp(64)
        mrow.add_widget(ccard)
        col.add_widget(mrow)

        # ---- Діти ----
        chead = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(6))
        chead.add_widget(lbl("ДІТИ", color=MUTED, size=11))
        add_btn = Pill(text="+ Додати", bg=CARD, fg=RED, border=BORDER,
                       size_hint_x=None, width=dp(96), font_size=sp(13))
        add_btn.bind(on_release=lambda *_: self.open_child(None))
        chead.add_widget(add_btn)
        col.add_widget(chead)

        self.children_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(7))
        self.children_box.bind(minimum_height=self.children_box.setter("height"))
        col.add_widget(self.children_box)

        # ---- Кнопка розрахунку ----
        calc_btn = Pill(text="Розрахувати", bg=RED, size_hint_y=None, height=dp(52),
                        font_size=sp(16), bold=True)
        calc_btn.bind(on_release=self.calculate)
        col.add_widget(calc_btn)

        # ---- Разом до виплати ----
        self.total_card = Card(bg=RED, border=None, padding=[dp(14), dp(14)], spacing=dp(2),
                               size_hint_y=None, height=dp(78))
        self.total_card.add_widget(lbl("Разом до виплати", color=(1, 0.87, 0.86, 1), size=12,
                                       size_hint_y=None, height=dp(18), halign="center"))
        self.total_value = lbl("—", color=(1, 1, 1, 1), size=26, bold=True, halign="center")
        self.total_card.add_widget(self.total_value)
        self.total_card.opacity = 0
        col.add_widget(self.total_card)

        # ---- Деталізація ----
        self.result_card = Card(padding=[dp(12), dp(12)], size_hint_y=None)
        self.result_lbl = lbl("", color=TEXT, size=12.5, size_hint_y=None)
        self.result_lbl.bind(texture_size=self._sync_result)
        self.result_card.add_widget(self.result_lbl)
        self.result_card.opacity = 0
        self.result_card.height = 0
        col.add_widget(self.result_card)

        # ---- Копіювати ----
        self.copy_btn = Pill(text="Копіювати результат", bg=CARD, fg=SUB, border=BORDER,
                             size_hint_y=None, height=dp(44), font_size=sp(14))
        self.copy_btn.bind(on_release=self.copy_result)
        self.copy_btn.opacity = 0
        col.add_widget(self.copy_btn)

        root.add_widget(col)
        self._result_str = ""
        self._refresh_children()
        return root

    def _sync_result(self, *a):
        self.result_lbl.height = self.result_lbl.texture_size[1]
        self.result_card.height = self.result_lbl.texture_size[1] + dp(24)

    # ---- налаштування ----
    def load_settings(self):
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                stavka = data.get("stavka", ДЕФОЛТ_СТАВКА)
                old_pm = data.get("pm")
                pm_do6 = data.get("pm_do6", old_pm if old_pm is not None else ДЕФОЛТ_ПМ_ДО6)
                pm_vid6 = data.get("pm_vid6", old_pm if old_pm is not None else ДЕФОЛТ_ПМ_ВІД6)
                return stavka, pm_do6, pm_vid6
            except Exception:
                pass
        return ДЕФОЛТ_СТАВКА, ДЕФОЛТ_ПМ_ДО6, ДЕФОЛТ_ПМ_ВІД6

    def save_settings_clicked(self, *_):
        try:
            stavka  = float(self.stavka_in.text.replace(",", "."))
            pm_do6  = float(self.pm_do6_in.text.replace(",", "."))
            pm_vid6 = float(self.pm_vid6_in.text.replace(",", "."))
        except ValueError:
            toast("Помилка", "Ставка та ПМ мають бути числами.")
            return
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump({"stavka": stavka, "pm_do6": pm_do6, "pm_vid6": pm_vid6},
                      f, ensure_ascii=False, indent=2)
        toast("Готово", "Налаштування збережено.")

    # ---- діти ----
    def load_children(self):
        if os.path.exists(self.children_path):
            try:
                with open(self.children_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                result = []
                for d in data:
                    result.append({
                        "name": d["name"],
                        "birth": date.fromisoformat(d["birth"]),
                        "start": date.fromisoformat(d["start"]),
                        "end": date.fromisoformat(d["end"]) if d.get("end") else None,
                        "invalid": d.get("invalid", False),
                    })
                return result
            except Exception:
                pass
        return []

    def save_children(self):
        data = [{
            "name": c["name"],
            "birth": c["birth"].isoformat(),
            "start": c["start"].isoformat(),
            "end": c["end"].isoformat() if c["end"] else None,
            "invalid": c["invalid"],
        } for c in self.children_list]
        with open(self.children_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def open_child(self, index):
        child = self.children_list[index] if index is not None else None

        def on_save(data):
            if index is None:
                self.children_list.append(data)
            else:
                self.children_list[index] = data
            self.save_children()
            self._refresh_children()

        ChildDialog(on_save, child).open()

    def _refresh_children(self):
        self.children_box.clear_widgets()
        self.count_lbl.text = str(len(self.children_list))
        if not self.children_list:
            empty = Card(padding=[dp(12), dp(14)], size_hint_y=None, height=dp(48))
            empty.add_widget(lbl("— дітей ще немає —", color=MUTED, size=13, halign="center"))
            self.children_box.add_widget(empty)
            return
        for i, c in enumerate(self.children_list):
            card = Card(orientation="horizontal", padding=[dp(11), dp(8)], spacing=dp(6),
                        size_hint_y=None, height=dp(56))
            info = BoxLayout(orientation="vertical")
            name_row = BoxLayout(size_hint_y=None, height=dp(20), spacing=dp(6))
            name_row.add_widget(lbl(c["name"], color=TEXT, size=13.5,
                                    size_hint_x=None, width=dp(120)))
            if c["invalid"]:
                tag = Pill(text="інв", bg=RED_BG, fg=RED, border=(0.93, 0.76, 0.75, 1),
                           radius=dp(5), size_hint_x=None, width=dp(38), font_size=sp(10))
                name_row.add_widget(tag)
            name_row.add_widget(Label())
            info.add_widget(name_row)
            end_s = c["end"].strftime("%d.%m.%Y") if c["end"] else "—"
            info.add_widget(lbl(f"нар. {c['birth'].strftime('%d.%m.%Y')} · "
                                f"{c['start'].strftime('%d.%m.%Y')} → {end_s}",
                                color=MUTED, size=11))
            card.add_widget(info)
            edit_b = Pill(text="ред.", bg=CARD, fg=SUB, border=BORDER,
                          size_hint_x=None, width=dp(48), font_size=sp(12))
            del_b  = Pill(text="✕", bg=CARD, fg=RED, border=BORDER,
                          size_hint_x=None, width=dp(40), font_size=sp(14))
            edit_b.bind(on_release=lambda _, idx=i: self.open_child(idx))
            del_b.bind(on_release=lambda _, idx=i: self._remove_child(idx))
            card.add_widget(edit_b)
            card.add_widget(del_b)
            self.children_box.add_widget(card)

    def _remove_child(self, index):
        self.children_list.pop(index)
        self.save_children()
        self._refresh_children()

    # ---- розрахунок ----
    def calculate(self, *_):
        try:
            stavka  = float(self.stavka_in.text.replace(",", "."))
            pm_do6  = float(self.pm_do6_in.text.replace(",", "."))
            pm_vid6 = float(self.pm_vid6_in.text.replace(",", "."))
            calc_dt = datetime.strptime(self.month_in.text.strip(), "%m.%Y")
        except ValueError:
            toast("Помилка", "Перевірте значення.\nМісяць — у форматі ММ.РРРР")
            return
        text, total = build_result(stavka, pm_do6, pm_vid6, self.children_list,
                                   calc_dt.year, calc_dt.month, self.month_in.text.strip())
        self._result_str = text
        self.total_value.text = f"{total:,.2f}".replace(",", " ") + " грн"
        self.result_lbl.text = text
        self.total_card.opacity = 1
        self.result_card.opacity = 1
        self.copy_btn.opacity = 1

    def copy_result(self, *_):
        if not self._result_str.strip():
            toast("Порожньо", "Спочатку виконайте розрахунок.")
            return
        Clipboard.copy(self._result_str)
        toast("Готово", "Результат скопійовано.")


if __name__ == "__main__":
    ZPApp().run()
