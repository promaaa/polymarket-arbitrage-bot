import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# Load data
try:
    with open('opportunities.json') as f:
        data = json.load(f)
except FileNotFoundError:
    print("Error: opportunities.json not found.")
    exit(1)

ops = data.get('opportunities', [])
if not ops:
    print("No opportunities found for analysis")
    exit(1)

# Filter for viable trades (simulating a configured bot)
df = pd.DataFrame(ops)
all_profits = df['profit_percentage']
# Only trade significant opportunities (> 0.2%)
# 0.1% is mostly noise/fees
profits = all_profits[all_profits >= 0.2] 

if len(profits) == 0:
    print("No profitable opportunities > 0.2% found. Using all.")
    profits = all_profits

print(f"Using {len(profits)}/{len(all_profits)} opportunities for simulation (Avg: {profits.mean():.2f}%)")

# Configuration
TURNOVERS_PER_DAY = 5  # Capital cycled 5 times per day
FAIL_RATE = 0.01       # 1% execution failure (Optimized)
FAIL_LOSS_PCT = 2.0    # 2% loss (Spread slippage) meaning 1 leg filled, other slipped

def simulate_day(capital, profits_pool, n_turnovers):
    daily_pnl = 0
    trade_size = capital 
    
    # Determine number of trades (Turnover * 1 trade per cap ?)
    # Assuming full capital deployed per trade sequentially
    n_trades = n_turnovers
    
    # Bootstrap sampling
    chosen_profits = np.random.choice(profits_pool, size=n_trades, replace=True)
    
    for p in chosen_profits:
        # Check failure event (Risk)
        if np.random.random() < FAIL_RATE:
            # Loss scenario
            pnl = -trade_size * (FAIL_LOSS_PCT / 100.0)
        else:
            # Profit scenario
            pnl = trade_size * (p / 100.0)
            
        daily_pnl += pnl
        
    return daily_pnl

# Simulation loop
investments = [100, 500, 1000, 2000, 5000]
results = []

print("Running Monte Carlo simulation...")
for inv in investments:
    # Simulate 1000 days
    sim_days = [simulate_day(inv, profits, TURNOVERS_PER_DAY) for _ in range(1000)]
    
    mean_daily = np.mean(sim_days)
    results.append({
        'Investment': inv,
        'Daily_Mean': mean_daily,
        'Daily_Min': np.percentile(sim_days, 5), # 5th percentile (Bad luck day)
        'Daily_Max': np.percentile(sim_days, 95),
        'Monthly_Proj': mean_daily * 30,
        'Yearly_Proj': mean_daily * 365,
        'Win_Rate_Days': sum(1 for d in sim_days if d > 0) / len(sim_days) * 100
    })

res_df = pd.DataFrame(results)

# Setup Plot
plt.figure(figsize=(16, 12))
sns.set_theme(style="whitegrid")

# 1. Daily Profit Expected vs Risk
plt.subplot(2, 2, 1)
ax1 = sns.barplot(data=res_df, x='Investment', y='Daily_Mean', color='seagreen', alpha=0.8)
# Add error bars
x_coords = range(len(investments))
plt.errorbar(x=x_coords, y=res_df['Daily_Mean'], 
             yerr=[res_df['Daily_Mean'] - res_df['Daily_Min'], res_df['Daily_Max'] - res_df['Daily_Mean']], 
             fmt='none', c='black', capsize=5, linewidth=1.5)
plt.title('Daily Profit Potential (Mean with 5th-95th Percentile Range)', fontsize=14)
plt.ylabel('Profit ($)')
plt.xlabel('Capital Invested ($)')
for i, v in enumerate(res_df['Daily_Mean']):
    ax1.text(i, v + (v*0.1), f"${v:.2f}", ha='center', fontweight='bold')

# 2. Cumulative Yearly Projection
plt.subplot(2, 2, 2)
ax2 = sns.barplot(data=res_df, x='Investment', y='Yearly_Proj', palette='viridis')
plt.title('Projected Yearly Profit (Non-Compounded)', fontsize=14)
plt.ylabel('Profit ($)')
plt.xlabel('Capital Invested ($)')
for i, v in enumerate(res_df['Yearly_Proj']):
    ax2.text(i, v, f"${v:,.0f}", ha='center', va='bottom', fontweight='bold')

# 3. Monthly Returns Distribution for $1000
plt.subplot(2, 1, 2)
# Simulate 10,000 months for $1000
inv_1000_days = [simulate_day(1000, profits, TURNOVERS_PER_DAY) for _ in range(30000)]
monthly_pnls = [sum(inv_1000_days[i:i+30]) for i in range(0, len(inv_1000_days), 30)]

sns.histplot(monthly_pnls, kde=True, color='dodgerblue', alpha=0.6, line_kws={'linewidth': 2})
plt.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Queries')
plt.axvline(x=np.mean(monthly_pnls), color='green', linestyle='--', linewidth=2, label=f'Mean: ${np.mean(monthly_pnls):.2f}')
plt.title('Risk Analysis: Monthly Return Distribution for $1,000 Capital', fontsize=14)
plt.xlabel('Monthly Profit ($)')
plt.legend()

# Save Stats to text
with open('profit_stats.txt', 'w') as f:
    f.write(res_df.to_string())

plt.suptitle('Polymarket Arbitrage Statistical Analysis', fontsize=20, y=0.98)
plt.tight_layout()
plt.savefig('profit_analysis.png', dpi=300)
print("Analysis complete. Saved 'profit_analysis.png' and 'profit_stats.txt'.")
