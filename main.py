"""
Програма розрахунку заробітної плати патронатного вихователя (GUI).
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import calendar
from datetime import date, datetime, timedelta

ДЕФОЛТ_СТАВКА = 8000.0
ДЕФОЛТ_ПМ_ДО6 = 2563.0      # прожитковий мінімум для дітей до 6 років
ДЕФОЛТ_ПМ_ВІД6 = 3028.0     # прожитковий мінімум для дітей від 6 до 18 років

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
CHILDREN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "children.json")


def load_settings():
    """Повертає (stavka, pm_do6, pm_vid6). Мігрує старий формат з єдиним 'pm'."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            stavka = data.get("stavka", ДЕФОЛТ_СТАВКА)
            # старий формат мав один "pm" — використовуємо його для обох категорій
            old_pm = data.get("pm")
            pm_do6 = data.get("pm_do6", old_pm if old_pm is not None else ДЕФОЛТ_ПМ_ДО6)
            pm_vid6 = data.get("pm_vid6", old_pm if old_pm is not None else ДЕФОЛТ_ПМ_ВІД6)
            return stavka, pm_do6, pm_vid6
        except Exception:
            pass
    return ДЕФОЛТ_СТАВКА, ДЕФОЛТ_ПМ_ДО6, ДЕФОЛТ_ПМ_ВІД6


def save_settings(stavka, pm_do6, pm_vid6):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"stavka": stavka, "pm_do6": pm_do6, "pm_vid6": pm_vid6},
                  f, ensure_ascii=False, indent=2)


def load_children():
    """Завантажує збережений список дітей (щоб не вводити щоразу заново)."""
    if os.path.exists(CHILDREN_FILE):
        try:
            with open(CHILDREN_FILE, "r", encoding="utf-8") as f:
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


def save_children(children):
    data = [{
        "name": c["name"],
        "birth": c["birth"].isoformat(),
        "start": c["start"].isoformat(),
        "end": c["end"].isoformat() if c["end"] else None,
        "invalid": c["invalid"],
    } for c in children]
    with open(CHILDREN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================
# Формули розрахунку
# =========================
def child_days_in_month(start: date, end, calc_year: int, calc_month: int) -> int:
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


def sixth_birthday(birth: date) -> date:
    """Дата 6-річчя. Для народжених 29 лютого — 28 лютого відповідного року."""
    try:
        return date(birth.year + 6, birth.month, birth.day)
    except ValueError:
        return date(birth.year + 6, birth.month, 28)


def child_days_split_by_age(start: date, end, birth: date, calc_year: int, calc_month: int):
    """
    Дні перебування дитини у місяці, розбиті на (до 6 років, від 6 років).
    День 6-річчя і далі рахується як «від 6 років».
    """
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
        return 0, total            # весь період — дитині вже 6+
    if sixth > d_to:
        return total, 0            # весь період — дитині ще менше 6
    days_under = (sixth - d_from).days   # дні строго до 6-річчя
    return days_under, total - days_under


def calc_child_support(pm_do6: float, pm_vid6: float, start: date, end, birth: date,
                       invalid: bool, calc_year: int, calc_month: int) -> float:
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    d_under, d_over = child_days_split_by_age(start, end, birth, calc_year, calc_month)
    multiplier = 3.5 if invalid else 2.5
    return (pm_do6 * multiplier * d_under + pm_vid6 * multiplier * d_over) / days_in_month


def is_under1(birth: date, calc_year: int, calc_month: int) -> bool:
    """Чи дитині ще немає 1 року на початок розрахункового місяця (визначається автоматично)."""
    month_start = date(calc_year, calc_month, 1)
    try:
        first_bday = date(birth.year + 1, birth.month, birth.day)
    except ValueError:
        first_bday = date(birth.year + 1, birth.month, 28)
    return first_bday > month_start


def calc_total_child_days(children: list, calc_year: int, calc_month: int) -> int:
    """Сума днів перебування всіх дітей у місяці (для надбавки по днях)."""
    return sum(child_days_in_month(c["start"], c["end"], calc_year, calc_month) for c in children)


def calc_bonus_segments(base_3: float, children: list, calc_year: int, calc_month: int):
    """
    Надбавка до ЗП рахується ПО ДНЯХ і розбивається на періоди за кількістю дітей.
    За кожен день місяця +10% за кожну дитину, що була того дня.

    Повертає (список_сегментів, сума_надбавки_грн), де кожен сегмент — dict:
      count  – кількість дітей у ці дні
      pct    – відсоток надбавки (count * 10)
      days   – скільки днів місяця було саме стільки дітей
      amount – сума надбавки за ці дні (грн)

    Приклад: 17 днів було 4 дитини (+40%) і 13 днів — 3 дитини (+30%) →
    показуються два окремі рядки з сумами, а не один усереднений.
    """
    days_in_month = calendar.monthrange(calc_year, calc_month)[1]
    # кількість дітей за кожен день місяця
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


def calc_salary_breakdown(stavka: float, total_bonus_pct: int, children: list,
                          calc_year: int, calc_month: int) -> dict:
    """
    Грошове забезпечення вихователя:
      — є хоча б одна дитина в розрахунковому місяці: базові 3 ставки (+ надбавка);
      — немає жодної дитини: не нараховується (0).
    Пільговий 7-денний термін не застосовується.
    """
    has_child = any(child_days_in_month(c["start"], c["end"], calc_year, calc_month) > 0
                    for c in children)
    if not has_child:
        return {"normal": 0.0, "low": 0.0,
                "note": "немає дітей у місяці — забезпечення не нараховується"}
    normal_full = stavka * 3 * (1 + total_bonus_pct / 100)
    return {"normal": normal_full, "low": 0.0, "note": ""}


# =========================
# Діалог додавання / редагування дитини
# =========================
class ChildDialog(tk.Toplevel):
    def __init__(self, parent, child: dict = None):
        super().__init__(parent)
        is_edit = child is not None
        self.title("Редагувати дитину" if is_edit else "Додати дитину")
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        pad = {"padx": 10, "pady": 6}

        ttk.Label(self, text="Ім'я / ПІБ:").grid(row=0, column=0, sticky="w", **pad)
        self.name_var = tk.StringVar(value=child["name"] if is_edit else "")
        ttk.Entry(self, textvariable=self.name_var, width=28).grid(row=0, column=1, **pad)

        ttk.Label(self, text="Дата народження (ДД.ММ.РРРР):").grid(row=1, column=0, sticky="w", **pad)
        self.birth_var = tk.StringVar(
            value=child["birth"].strftime("%d.%m.%Y") if (is_edit and child.get("birth")) else "")
        ttk.Entry(self, textvariable=self.birth_var, width=14).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(self, text="(визначає ПМ: до 6 років / від 6 до 18 років)", foreground="gray",
                  font=("", 8)).grid(row=2, column=0, columnspan=2, padx=10, pady=0)

        ttk.Label(self, text="Дата прийняття (ДД.ММ.РРРР):").grid(row=3, column=0, sticky="w", **pad)
        self.start_var = tk.StringVar(
            value=child["start"].strftime("%d.%m.%Y") if is_edit else date.today().strftime("%d.%m.%Y"))
        ttk.Entry(self, textvariable=self.start_var, width=14).grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(self, text="Дата вибуття (ДД.ММ.РРРР):").grid(row=4, column=0, sticky="w", **pad)
        self.end_var = tk.StringVar(
            value=child["end"].strftime("%d.%m.%Y") if (is_edit and child["end"]) else "")
        ttk.Entry(self, textvariable=self.end_var, width=14).grid(row=4, column=1, sticky="w", **pad)
        ttk.Label(self, text="(залиште порожнім, якщо ще не вибув)", foreground="gray",
                  font=("", 8)).grid(row=5, column=0, columnspan=2, padx=10, pady=0)

        ttk.Separator(self, orient="horizontal").grid(row=6, column=0, columnspan=2,
                                                      sticky="ew", padx=10, pady=6)

        self.invalid_var = tk.BooleanVar(value=child["invalid"] if is_edit else False)
        ttk.Checkbutton(self, text="Інвалідність  (соціальна допомога 3.5 ПМ замість 2.5 ПМ)",
                        variable=self.invalid_var).grid(row=7, column=0, columnspan=2, sticky="w", **pad)

        ttk.Label(self, text="«До 1 року» визначається автоматично за датою народження.\n"
                             "Надбавка до грошового забезпечення: +10% за кожну дитину.",
                  foreground="gray", font=("", 8)).grid(row=8, column=0, columnspan=2, padx=10, pady=(0, 4))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=9, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Зберегти" if is_edit else "Додати", command=self.ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Скасувати", command=self.destroy).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window()

    def ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Помилка", "Введіть ім'я дитини.", parent=self)
            return
        try:
            birth = datetime.strptime(self.birth_var.get().strip(), "%d.%m.%Y").date()
        except ValueError:
            messagebox.showerror("Помилка", "Введіть дату народження у форматі ДД.ММ.РРРР",
                                 parent=self)
            return
        try:
            start = datetime.strptime(self.start_var.get().strip(), "%d.%m.%Y").date()
        except ValueError:
            messagebox.showerror("Помилка", "Невірний формат дати прийняття.\nВикористовуйте ДД.ММ.РРРР",
                                 parent=self)
            return
        if start < birth:
            messagebox.showerror("Помилка", "Дата прийняття не може бути раніше дати народження.",
                                 parent=self)
            return
        end = None
        raw_end = self.end_var.get().strip()
        if raw_end:
            try:
                end = datetime.strptime(raw_end, "%d.%m.%Y").date()
            except ValueError:
                messagebox.showerror("Помилка", "Невірний формат дати вибуття.\nВикористовуйте ДД.ММ.РРРР",
                                     parent=self)
                return
            if end < start:
                messagebox.showerror("Помилка", "Дата вибуття не може бути раніше дати прийняття.",
                                     parent=self)
                return
        self.result = {
            "name": name, "birth": birth, "start": start, "end": end,
            "invalid": self.invalid_var.get(),
        }
        self.destroy()


# =========================
# Головне вікно
# =========================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Розрахунок грошового забезпечення патронатного вихователя")
        self.geometry("700x640")
        self.resizable(False, False)

        stavka, pm_do6, pm_vid6 = load_settings()
        self.children_list: list = load_children()

        # ---- Налаштування ----
        sf = ttk.LabelFrame(self, text="Налаштування (змінюються по закону)")
        sf.pack(fill="x", padx=10, pady=10)

        ttk.Label(sf, text="Ставка (грн):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.stavka_var = tk.StringVar(value=str(stavka))
        ttk.Entry(sf, textvariable=self.stavka_var, width=15).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(sf, text="ПМ, діти до 6 років (грн):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.pm_do6_var = tk.StringVar(value=str(pm_do6))
        ttk.Entry(sf, textvariable=self.pm_do6_var, width=15).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(sf, text="ПМ, діти 6–18 років (грн):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.pm_vid6_var = tk.StringVar(value=str(pm_vid6))
        ttk.Entry(sf, textvariable=self.pm_vid6_var, width=15).grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(sf, text="Зберегти налаштування", command=self.save_settings_clicked)\
            .grid(row=0, column=2, rowspan=3, padx=10, pady=5)

        # ---- Параметри ----
        pf = ttk.LabelFrame(self, text="Параметри розрахунку")
        pf.pack(fill="x", padx=10, pady=5)

        ttk.Label(pf, text="Розрахунковий місяць (ММ.РРРР):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.month_var = tk.StringVar(value=date.today().strftime("%m.%Y"))
        ttk.Entry(pf, textvariable=self.month_var, width=10).grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # ---- Діти ----
        cf = ttk.LabelFrame(self, text="Діти")
        cf.pack(fill="x", padx=10, pady=5)

        btn_row = ttk.Frame(cf)
        btn_row.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_row, text="+ Додати", command=self.add_child).pack(side="left", padx=4)
        self.edit_btn = ttk.Button(btn_row, text="Редагувати", command=self.edit_child, state="disabled")
        self.edit_btn.pack(side="left", padx=4)
        self.remove_btn = ttk.Button(btn_row, text="− Видалити", command=self.remove_child, state="disabled")
        self.remove_btn.pack(side="left", padx=4)

        cols = ("name", "birth", "start", "end", "invalid")
        self.tree = ttk.Treeview(cf, columns=cols, show="headings", height=5)
        self.tree.heading("name",    text="Ім'я / ПІБ")
        self.tree.heading("birth",   text="Народження")
        self.tree.heading("start",   text="Прийнятий")
        self.tree.heading("end",     text="Вибув")
        self.tree.heading("invalid", text="Інвалідність")
        self.tree.column("name",    width=200)
        self.tree.column("birth",   width=100, anchor="center")
        self.tree.column("start",   width=100, anchor="center")
        self.tree.column("end",     width=100, anchor="center")
        self.tree.column("invalid", width=95,  anchor="center")
        self.tree.pack(fill="x", padx=5, pady=(0, 5))
        self.tree.bind("<Double-1>", lambda _: self.edit_child())

        # ---- Кнопка розрахунку ----
        ttk.Button(self, text="Розрахувати", command=self.calculate).pack(pady=8)

        # ---- Результат ----
        rf = ttk.LabelFrame(self, text="Результат")
        rf.pack(fill="both", expand=True, padx=10, pady=5)
        self.result_text = tk.Text(rf, height=9, wrap="word")
        self.result_text.pack(fill="both", expand=True, padx=5, pady=(5, 0))
        self.result_text.config(state="disabled")
        # дозволяємо виділяти й копіювати текст (Ctrl+C / Ctrl+A), але не редагувати
        self.result_text.bind("<Control-c>", lambda e: None)
        self.result_text.bind("<Control-a>",
                              lambda e: (self.result_text.tag_add("sel", "1.0", "end"), "break")[1])

        ttk.Button(rf, text="Копіювати результат", command=self.copy_result)\
            .pack(anchor="e", padx=5, pady=5)

        # показуємо збережених дітей
        self._refresh_tree()

    # ---- Helpers ----
    def _refresh_tree(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for c in self.children_list:
            self.tree.insert("", tk.END, values=(
                c["name"],
                c["birth"].strftime("%d.%m.%Y") if c.get("birth") else "—",
                c["start"].strftime("%d.%m.%Y"),
                c["end"].strftime("%d.%m.%Y") if c["end"] else "—",
                "✓" if c["invalid"] else "—",
            ))
        has = len(self.children_list) > 0
        self.edit_btn.config(state="normal"   if has else "disabled")
        self.remove_btn.config(state="normal" if has else "disabled")

    def _selected_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return list(self.tree.get_children()).index(sel[0])

    # ---- Actions ----
    def add_child(self):
        dlg = ChildDialog(self)
        if dlg.result:
            self.children_list.append(dlg.result)
            save_children(self.children_list)
            self._refresh_tree()

    def edit_child(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Увага", "Оберіть дитину зі списку.")
            return
        dlg = ChildDialog(self, self.children_list[idx])
        if dlg.result:
            self.children_list[idx] = dlg.result
            save_children(self.children_list)
            self._refresh_tree()

    def remove_child(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showwarning("Увага", "Оберіть дитину для видалення.")
            return
        self.children_list.pop(idx)
        save_children(self.children_list)
        self._refresh_tree()

    def save_settings_clicked(self):
        try:
            stavka  = float(self.stavka_var.get().replace(",", "."))
            pm_do6  = float(self.pm_do6_var.get().replace(",", "."))
            pm_vid6 = float(self.pm_vid6_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Помилка", "Ставка та ПМ мають бути числами.")
            return
        save_settings(stavka, pm_do6, pm_vid6)
        messagebox.showinfo("Готово", "Налаштування збережено.")

    def copy_result(self):
        text = self.result_text.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showinfo("Порожньо", "Спочатку виконайте розрахунок.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Готово", "Результат скопійовано в буфер обміну.")

    def calculate(self):
        try:
            stavka  = float(self.stavka_var.get().replace(",", "."))
            pm_do6  = float(self.pm_do6_var.get().replace(",", "."))
            pm_vid6 = float(self.pm_vid6_var.get().replace(",", "."))
            calc_dt = datetime.strptime(self.month_var.get().strip(), "%m.%Y")
            calc_year, calc_month = calc_dt.year, calc_dt.month
        except ValueError:
            messagebox.showerror("Помилка", "Перевірте значення.\nМісяць вводьте у форматі ММ.РРРР")
            return

        days_in_month = calendar.monthrange(calc_year, calc_month)[1]
        base_3 = stavka * 3
        # базова ЗП без надбавки (3 ставки / 1 ставка / пільговий 7 днів)
        sal = calc_salary_breakdown(stavka, 0, self.children_list, calc_year, calc_month)
        base_salary = sal["normal"] + sal["low"]
        # надбавка рахується ПО ДНЯХ, з розбивкою по періодах за кількістю дітей
        bonus_segments, bonus_amount = calc_bonus_segments(base_3, self.children_list, calc_year, calc_month)
        caregiver_zp = base_salary + bonus_amount

        child_lines   = []
        total_support = 0.0
        for c in self.children_list:
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
                age_note = f"{mult}: до 6р {d_under} дн. + 6–18р {d_over} дн."
            elif d_under > 0:
                age_note = f"{mult}, до 6 років"
            elif d_over > 0:
                age_note = f"{mult}, 6–18 років"
            else:
                age_note = mult
            child_lines.append(f"  {c['name']}{flag_str}  ({note}, {age_note}):  {amount:.2f} грн")

        total = caregiver_zp + total_support

        # --- Блок грошового забезпечення вихователя ---
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
                lines.append(f"    +{s['pct']}% ({s['count']} дит. × {s['days']} дн.):  {s['amount']:.2f} грн")
            if len(bonus_segments) > 1:
                lines.append(f"    Разом надбавка:  {bonus_amount:.2f} грн")
        lines.append(f"  Разом грошове забезпечення:  {caregiver_zp:.2f} грн")
        zp_block = "\n".join(lines)

        result = (
            f"Розрахунковий місяць: {self.month_var.get().strip()}  ({days_in_month} дн.)\n"
            f"Ставка: {stavka:.2f} грн  |  ПМ до 6р: {pm_do6:.2f} грн  |  ПМ 6–18р: {pm_vid6:.2f} грн\n\n"
            f"{zp_block}\n\n"
            f"Соціальна допомога на дітей (2.5 ПМ, для дітей-інвалідів — 3.5 ПМ):\n"
            + ("\n".join(child_lines) if child_lines else "  — дітей немає")
            + f"\n  Разом соціальна допомога:  {total_support:.2f} грн\n\n"
            f"РАЗОМ: {total:.2f} грн"
        )

        self.result_text.config(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, result)
        self.result_text.config(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
