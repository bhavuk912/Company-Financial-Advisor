import threading
import requests
from bs4 import BeautifulSoup
import pandas as pd
from io import StringIO
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import messagebox

# --- Root Window ---
root = tk.Tk()
root.title("\U0001F4CA Company Financial Analyzer")
root.geometry("1024x768")
root.config(bg="#1e1e1e")

# --- Frame Setup ---
frames = {}
for name in ["welcome", "input", "result"]:
    frames[name] = tk.Frame(root, bg="#1e1e1e")

def show_frame(name):
    for f in frames.values():
        f.pack_forget()
    frames[name].pack(fill='both', expand=True)

# --- Welcome Page ---
def show_input_page():
    show_frame("input")

tk.Label(frames["welcome"], text="📊 Welcome to Financial Analyzer", font=("Segoe UI", 24, "bold"),
         bg="#1e1e1e", fg="white").pack(pady=60)

tk.Button(frames["welcome"], text="Start Analyzing", font=("Segoe UI", 14),
          bg="#007acc", fg="white", padx=20, pady=10,
          command=show_input_page).pack()

# --- Input Page ---
tk.Label(frames["input"], text="Enter Company Slug (e.g., TCS):", font=("Segoe UI", 14),
         bg="#1e1e1e", fg="white").pack(pady=20)

entry = tk.Entry(frames["input"], font=("Segoe UI", 14), bg="#2e2e2e", fg="white", insertbackground="white", width=30)
entry.pack(pady=10)

def start_analysis():
    company_slug = entry.get().strip().upper()
    if not company_slug:
        messagebox.showwarning("Input Required", "Please enter a company slug.")
        return
    threading.Thread(target=lambda: run_analysis_in_thread(company_slug), daemon=True).start()

tk.Button(frames["input"], text="Analyze", font=("Segoe UI", 12, "bold"), bg="#007acc", fg="white",
          activebackground="#005f9e", activeforeground="white", bd=0, relief="flat",
          padx=25, pady=12, command=start_analysis).pack(pady=20)

# --- Globals for Result Page ---
bullet_frame = None
result_text = None
graph_frame = None
graph_canvas = None

# --- Scraping + Analysis ---
def analyze_data(company_slug):
    url = f"https://www.screener.in/company/{company_slug}/"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {"error": f"Failed to fetch data. Status Code: {response.status_code}"}

    soup = BeautifulSoup(response.text, 'html.parser')
    try:
        pl_table = soup.find("section", {"id": "profit-loss"}).find("table")
        bs_table = soup.find("section", {"id": "balance-sheet"}).find("table")
    except:
        return {"error": "Could not locate financial tables on page."}

    try:
        pl_df = pd.read_html(StringIO(str(pl_table)))[0]
        bs_df = pd.read_html(StringIO(str(bs_table)))[0]
    except:
        return {"error": "Error reading financial tables into DataFrames."}

    def find_row(df, keyword):
        return df[df[df.columns[0]].str.lower().str.contains(keyword, na=False)]

    def clean_numeric(df):
        df_clean = df.copy()
        for col in df_clean.columns[1:]:
            df_clean[col] = df_clean[col].replace(r"[^0-9\-]", "", regex=True).replace('', '0')
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
        return df_clean

    try:
        sales = clean_numeric(find_row(pl_df, "sales"))
        net_profit = clean_numeric(find_row(pl_df, "net profit|profit after tax"))
        equity = clean_numeric(find_row(bs_df, "equity share capital|equity capital"))
        reserves = clean_numeric(find_row(bs_df, "reserves"))
        total_assets = clean_numeric(find_row(bs_df, "total assets|total liabilities"))
    except:
        return {"error": "Required financial rows not found or could not be parsed."}

    # Check for empty dataframes
    for df, name in [(sales, "Sales"), (net_profit, "Net Profit"), (equity, "Equity"), (reserves, "Reserves"), (total_assets, "Total Assets")]:
        if df.empty or df.shape[0] == 0:
            return {"error": f"{name} data not found for company '{company_slug}'."}

    all_cols = [col for col in sales.columns[1:] if 'TTM' not in col]
    year_map = {col: re.sub(r'\D', '', col) for col in all_cols}
    sorted_years = sorted(year_map.values(), reverse=True)[:5]
    final_cols = [col for col in all_cols if year_map[col] in sorted_years]
    final_years = [year_map[col] for col in final_cols]

    try:
        revenue = {year_map[col]: int(sales.iloc[0][col]) for col in final_cols}
        net_profit_dict = {year_map[col]: int(net_profit.iloc[0][col]) for col in final_cols}
        equity_share_capital = {year_map[col]: int(equity.iloc[0][col]) for col in final_cols}
        reserves_dict = {year_map[col]: int(reserves.iloc[0][col]) for col in final_cols}
        total_assets_dict = {year_map[col]: int(total_assets.iloc[0][col]) for col in final_cols}
        shareholder_equity = {
            year_map[col]: equity.iloc[0][col] + reserves.iloc[0][col]
            for col in final_cols
        }
    except IndexError:
        return {"error": f"Data for some years could not be parsed correctly from Screener.in."}

    roe_dict = {year: round((net_profit_dict[year] / shareholder_equity[year]) * 100, 2) if shareholder_equity[year] > 0 else None for year in sorted_years}
    roi_dict = {year: round((net_profit_dict[year] / total_assets_dict[year]) * 100, 2) if total_assets_dict[year] > 0 else None for year in sorted_years}
    financial_leverage = {year: round((total_assets_dict[year] / shareholder_equity[year]), 2) if shareholder_equity[year] > 0 else None for year in sorted_years}

    def format_with_suffix(value):
        if value >= 10000000:
            return f"{round(value / 10000000, 1)}Cr"
        elif value >= 100000:
            return f"{round(value / 100000, 1)}L"
        elif value >= 1000:
            return f"{round(value / 1000, 1)}K"
        else:
            return str(value)

    def y_axis_formatter(ax):
        ax.set_yticklabels([format_with_suffix(y) for y in ax.get_yticks()])

    def bar(ax, title, data, color, is_crore=False):
        keys = sorted_years[::-1]
        values = [data.get(k, 0) for k in keys]
        bars = ax.bar(keys, values, color=color, width=0.2)
        title_suffix = " (₹ Cr)" if is_crore else ""
        ax.set_title(title + title_suffix, color='white', fontsize=11)
        ax.tick_params(axis='x', rotation=0, colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.set_facecolor('#1e1e1e')
        y_axis_formatter(ax)
        for i, (bar, value) in enumerate(zip(bars, values)):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), format_with_suffix(value),
                    ha='center', va='bottom', fontsize=8, color='white', rotation=0)

    def plot_metrics():
        fig, axs = plt.subplots(2, 3, figsize=(13, 6))
        bar(axs[0, 0], "Revenue", revenue, '#66c2a5', is_crore=True)
        bar(axs[0, 1], "Net Profit", net_profit_dict, '#fc8d62', is_crore=True)
        bar(axs[0, 2], "Total Assets", total_assets_dict, '#8da0cb', is_crore=True)
        bar(axs[1, 0], "ROE (%)", roe_dict, '#e78ac3')
        bar(axs[1, 1], "ROI (%)", roi_dict, '#a6d854')
        bar(axs[1, 2], "Fin. Leverage", financial_leverage, '#ffd92f')
        fig.patch.set_facecolor('#1e1e1e')
        plt.tight_layout(pad=2.0)
        return fig

    return {
        "fig": plot_metrics(),
        "roe_dict": roe_dict,
        "roi_dict": roi_dict,
        "error": None
    }

# --- GUI Update ---
def compare_and_feedback(metric_dict, label):
    y1, y2 = "2021", "2025"
    if y1 not in metric_dict or y2 not in metric_dict:
        return f"• {label} data not available for comparison."
    v1, v2 = metric_dict[y1], metric_dict[y2]
    diff = round(v2 - v1, 2)
    direction = "risen" if diff > 0 else "fallen" if diff < 0 else "remained the same"
    abs_diff = abs(diff)
    if diff == 0:
        feedback = "remained stable with minimal change."

# Negative direction (decline)
    elif diff < -100:
        feedback = "has collapsed catastrophically — performance has deteriorated beyond typical bounds."
    elif -100 <= diff < -50:
        feedback = "plunged severely — this indicates extreme financial distress."
    elif -50 <= diff < -30:
        feedback = "fell drastically — suggests a major weakness in performance."
    elif -30 <= diff < -20:
        feedback = "declined substantially — a red flag worth investigating."
    elif -20 <= diff < -15:
        feedback = "dropped heavily — possibly due to internal or market issues."
    elif -15 <= diff < -10:
        feedback = "fell sharply — negative trend is clearly visible."
    elif -10 <= diff < -7:
        feedback = "declined significantly — consider examining the cause."
    elif -7 <= diff < -5:
        feedback = "moderately declined — could reflect early signs of weakness."
    elif -5 <= diff < -3:
        feedback = "noticeably declined — monitor closely."
    elif -3 <= diff < -2:
        feedback = "slightly declined — not alarming but worth attention."
    elif -2 <= diff < -1:
        feedback = "marginally decreased — almost stable."
    elif -1 <= diff < 0:
        feedback = "barely changed — nearly flat movement."

    # Positive direction (growth)
    elif 0 < diff <= 1:
        feedback = "barely changed — nearly flat movement."
    elif 1 < diff <= 2:
        feedback = "marginally improved — almost stable."
    elif 2 < diff <= 3:
        feedback = "slightly improved — early growth signs."
    elif 3 < diff <= 5:
        feedback = "noticeably improved — some positive development."
    elif 5 < diff <= 7:
        feedback = "moderately improved — momentum is building."
    elif 7 < diff <= 10:
        feedback = "significantly increased — a strong trend upward."
    elif 10 < diff <= 15:
        feedback = "grew sharply — positive direction is clear."
    elif 15 < diff <= 20:
        feedback = "improved strongly — may reflect strategic success."
    elif 20 < diff <= 30:
        feedback = "rose substantially — indicates strong financial growth."
    elif 30 < diff <= 50:
        feedback = "surged impressively — transformation in performance."
    elif 50 < diff <= 100:
        feedback = "skyrocketed — business is thriving exceptionally."
    elif diff > 100:
        feedback = "exploded upward — extraordinary results, investigate for unusual gains."

    # Fallback
    else:
        feedback = "changed in an unexpected way — further verification recommended."

    return f"• {label} has {direction} from {v1:.2f}% in {y1} to {v2:.2f}% in {y2} ({diff:+.2f} percentage points). It {feedback}"

def update_gui(result):
    global bullet_frame, result_text, graph_frame, graph_canvas
    if result.get("error"):
        messagebox.showerror("Error", result["error"])
        return
    show_frame("result")
    if bullet_frame:
        bullet_frame.destroy()
    if graph_frame:
        graph_frame.destroy()

    bullet_frame = tk.Frame(frames["result"], bg="#1e1e1e")
    bullet_frame.pack(pady=10)

    result_text = tk.Text(bullet_frame, height=6, width=90, wrap="word",
                          font=("Segoe UI", 12), bg="#2e2e2e", fg="white")
    result_text.pack(padx=10, pady=10)
    result_text.configure(state="normal")
    result_text.delete("1.0", tk.END)

    summary = [
        compare_and_feedback(result["roe_dict"], "ROE"),
        compare_and_feedback(result["roi_dict"], "ROI")
    ]

    for point in summary:
        result_text.insert(tk.END, point + "\n")
    result_text.configure(state="disabled")

    graph_frame = tk.Frame(frames["result"], bg="#1e1e1e")
    graph_frame.pack(pady=10)

    fig = result["fig"]
    graph_canvas = FigureCanvasTkAgg(fig, master=graph_frame)
    graph_canvas.draw()
    graph_canvas.get_tk_widget().pack()

    def go_back_to_input():
        show_frame("input")
        entry.delete(0, tk.END)

    tk.Button(frames["result"], text="Analyze Another Company",
              font=("Segoe UI", 12), bg="#444", fg="white",
              padx=15, pady=8, command=go_back_to_input).pack(pady=15)

# --- Thread Wrapper ---
def run_analysis_in_thread(company_slug):
    result = analyze_data(company_slug)
    root.after(0, lambda: update_gui(result))

# --- Start GUI ---
show_frame("welcome")
root.mainloop()
