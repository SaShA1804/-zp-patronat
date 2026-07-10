"""
Розрахунок ЗП патронатного вихователя — мобільна версія (Kivy / Android).
Логіка розрахунку ідентична десктопній програмі.
"""

import os
import json
import calendar
from datetime import date, datetime, timedelta

from kivy.app import App
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.popup import Popup

ДЕФОЛТ_СТАВКА = 8000.0
ДЕФОЛТ_ПМ_ДО6 = 2563.0      # прожитковий мінімум для дітей до 6 років
ДЕФОЛТ_ПМ_ВІД6 = 3028.0     # прожитковий мінімум для дітей від 6 до 18 років


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
    """Чи дитині ще немає 1 року на початок розрахункового місяця (автоматично)."""
    month_start = date(calc_year, calc_month, 1)
    try:
        first_bday = date(birth.year + 1, birth.month, birth.day)
    except ValueError:
        first_bday = date(birth.year + 1, birth.month, 28)
    return first_bday > month_start


def calc_total_child_days(children, calc_year, calc_month):
    """Сума днів перебування всіх дітей у місяці (для надбавки по днях)."""
    return sum(child_days_in_month(c["start"], c["end"], calc_year, calc_month) for c in children)


def calc_bonus_segments(base_3, children, calc_year, calc_month):
    """
    Надбавка до ЗП рахується ПО ДНЯХ і розбивається на періоди за кількістю дітей.
    Повертає (список_сегментів, сума_надбавки_грн); сегмент: count, pct, days, amount.
    """
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
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    month_start   = date(calc_year, calc_month, 1)
    month_end     = date(calc_year, calc_month, days_in_month)

    normal_full = stavka * 3 * (1 + total_bonus_pct / 100)
    relevant = [c for c in children if c["start"] <= month_end]

    if not relevant:
        return {"normal": 0.0, "low": stavka, "note": "немає дітей — 1 ставка"}

    has_active = any(c["end"] is None or c["end"] >= month_end for c in relevant)
    if has_active:
        return {"normal": normal_full, "low": 0.0, "note": ""}

    last_dep  = max(c["end"] for c in relevant if c["end"] is not None)
    grace_end = last_dep + timedelta(days=7)

    if grace_end < month_start:
        return {"normal": 0.0, "low": stavka,
                "note": f"пільговий термін закінчився {grace_end.strftime('%d.%m.%Y')} — 1 ставка"}

    if grace_end >= month_end:
        return {"normal": normal_full, "low": 0.0,
                "note": f"пільговий 7 днів (діє до {grace_end.strftime('%d.%m.%Y')})"}

    grace_days = (grace_end - month_start).days + 1
    low_days   = days_in_month - grace_days
    return {
        "normal": normal_full * grace_days / days_in_month,
        "low":    stavka      * low_days   / days_in_month,
        "note":   (f"пільговий 7 днів по {grace_end.strftime('%d.%m.%Y')} "
                   f"({grace_days} дн.) + 1 ставка ({low_days} дн.)")
    }


def build_result_text(stavka, pm_do6, pm_vid6, children, calc_year, calc_month, month_str):
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    base_3 = stavka * 3
    # базова ЗП без надбавки (3 ставки / 1 ставка / пільговий 7 днів)
    sal = calc_salary_breakdown(stavka, 0, children, calc_year, calc_month)
    base_salary = sal["normal"] + sal["low"]
    # надбавка рахується ПО ДНЯХ, з розбивкою по періодах за кількістю дітей
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

    return (
        f"Розрахунковий місяць: {month_str}  ({days_in_month} дн.)\n"
        f"Ставка: {stavka:.2f} грн\n"
        f"ПМ до 6р: {pm_do6:.2f} грн | ПМ 6-18р: {pm_vid6:.2f} грн\n\n"
        f"{zp_block}\n\n"
        f"Соціальна допомога на дітей (2.5 ПМ, для дітей-інвалідів — 3.5 ПМ):\n"
        + ("\n".join(child_lines) if child_lines else "  — дітей немає")
        + f"\n  Разом соціальна допомога:  {total_support:.2f} грн\n\n"
        f"РАЗОМ: {total:.2f} грн"
    )


# =========================
# Спливаюче повідомлення
# =========================
def toast(title, text):
    content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
    content.add_widget(Label(text=text, halign="center"))
    btn = Button(text="OK", size_hint_y=None, height=dp(44))
    content.add_widget(btn)
    p = Popup(title=title, content=content, size_hint=(0.85, None), height=dp(200))
    btn.bind(on_release=p.dismiss)
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
        self.size_hint = (0.95, 0.9)

        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))

        def field(label, value):
            grid.add_widget(Label(text=label, size_hint_y=None, height=dp(24),
                                  halign="left", color=(0.9, 0.9, 0.9, 1)))
            ti = TextInput(text=value, multiline=False, size_hint_y=None, height=dp(44))
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

        # чекбокси
        def checkbox_row(text, active):
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            cb = CheckBox(active=active, size_hint_x=None, width=dp(40))
            row.add_widget(cb)
            row.add_widget(Label(text=text, halign="left"))
            grid.add_widget(row)
            return cb

        self.invalid_cb = checkbox_row("Інвалідність (соц. допомога 3.5 ПМ)", child["invalid"] if is_edit else False)
        grid.add_widget(Label(text="«До 1 року» — автоматично за датою народження.\n"
                                   "Надбавка до грошового забезпечення: +10% за дитину.",
                              size_hint_y=None, height=dp(44), font_size=dp(11),
                              color=(0.6, 0.6, 0.6, 1)))

        scroll = ScrollView()
        scroll.add_widget(grid)
        root.add_widget(scroll)

        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        save_btn = Button(text="Зберегти" if is_edit else "Додати")
        cancel_btn = Button(text="Скасувати")
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
        Window.softinput_mode = "below_target"
        self.settings_path = os.path.join(self.user_data_dir, "settings.json")
        self.children_path = os.path.join(self.user_data_dir, "children.json")
        self.children_list = self.load_children()
        stavka, pm_do6, pm_vid6 = self.load_settings()

        root = ScrollView()
        col = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8),
                        size_hint_y=None)
        col.bind(minimum_height=col.setter("height"))

        def header(text):
            col.add_widget(Label(text=f"[b]{text}[/b]", markup=True, size_hint_y=None,
                                 height=dp(30), halign="left", color=(0.85, 0.5, 0.5, 1)))

        def labeled_input(text, value):
            col.add_widget(Label(text=text, size_hint_y=None, height=dp(24), halign="left"))
            ti = TextInput(text=str(value), multiline=False, size_hint_y=None, height=dp(44),
                           input_type="number")
            col.add_widget(ti)
            return ti

        # --- Налаштування ---
        header("Налаштування (змінюються по закону)")
        self.stavka_in  = labeled_input("Ставка (грн):", stavka)
        self.pm_do6_in  = labeled_input("ПМ, діти до 6 років (грн):", pm_do6)
        self.pm_vid6_in = labeled_input("ПМ, діти 6-18 років (грн):", pm_vid6)
        save_set = Button(text="Зберегти налаштування", size_hint_y=None, height=dp(44))
        save_set.bind(on_release=self.save_settings_clicked)
        col.add_widget(save_set)

        # --- Місяць ---
        header("Параметри розрахунку")
        col.add_widget(Label(text="Розрахунковий місяць (ММ.РРРР):", size_hint_y=None,
                             height=dp(24), halign="left"))
        self.month_in = TextInput(text=date.today().strftime("%m.%Y"), multiline=False,
                                  size_hint_y=None, height=dp(44))
        col.add_widget(self.month_in)

        # --- Діти ---
        header("Діти")
        add_btn = Button(text="+ Додати дитину", size_hint_y=None, height=dp(44))
        add_btn.bind(on_release=lambda *_: self.open_child(None))
        col.add_widget(add_btn)

        self.children_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.children_box.bind(minimum_height=self.children_box.setter("height"))
        col.add_widget(self.children_box)

        # --- Розрахунок ---
        calc_btn = Button(text="РОЗРАХУВАТИ", size_hint_y=None, height=dp(52),
                          background_color=(0.7, 0.2, 0.2, 1))
        calc_btn.bind(on_release=self.calculate)
        col.add_widget(calc_btn)

        # --- Результат ---
        header("Результат")
        self.result_in = TextInput(text="", readonly=True, size_hint_y=None, height=dp(320),
                                    font_size=dp(13))
        col.add_widget(self.result_in)
        copy_btn = Button(text="Копіювати результат", size_hint_y=None, height=dp(44))
        copy_btn.bind(on_release=self.copy_result)
        col.add_widget(copy_btn)

        root.add_widget(col)
        self._refresh_children()
        return root

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
        """Завантажує збережений список дітей (щоб не вводити щоразу заново)."""
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
        if not self.children_list:
            lbl = Label(text="— дітей ще немає —", size_hint_y=None, height=dp(30),
                        color=(0.6, 0.6, 0.6, 1))
            self.children_box.add_widget(lbl)
            return
        for i, c in enumerate(self.children_list):
            row = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(4))
            end_s = c["end"].strftime("%d.%m.%Y") if c["end"] else "—"
            fl = "  [інв]" if c["invalid"] else ""
            info = (f"{c['name']}{fl}\n"
                    f"нар. {c['birth'].strftime('%d.%m.%Y')} | {c['start'].strftime('%d.%m.%Y')} → {end_s}")
            row.add_widget(Label(text=info, halign="left", valign="middle", font_size=dp(12),
                                 text_size=(Window.width * 0.55, None)))
            edit_b = Button(text="✎", size_hint_x=None, width=dp(48))
            del_b  = Button(text="✕", size_hint_x=None, width=dp(48),
                            background_color=(0.7, 0.2, 0.2, 1))
            edit_b.bind(on_release=lambda _, idx=i: self.open_child(idx))
            del_b.bind(on_release=lambda _, idx=i: self._remove_child(idx))
            row.add_widget(edit_b)
            row.add_widget(del_b)
            self.children_box.add_widget(row)

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
        text = build_result_text(stavka, pm_do6, pm_vid6, self.children_list,
                                 calc_dt.year, calc_dt.month, self.month_in.text.strip())
        self.result_in.text = text

    def copy_result(self, *_):
        if not self.result_in.text.strip():
            toast("Порожньо", "Спочатку виконайте розрахунок.")
            return
        Clipboard.copy(self.result_in.text)
        toast("Готово", "Результат скопійовано.")


if __name__ == "__main__":
    ZPApp().run()
