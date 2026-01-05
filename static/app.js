/**
 * Polymarket Arbitrage Bot - Dashboard JavaScript
 */

const API = {
    async getStats() {
        const res = await fetch('/api/stats');
        return res.json();
    },
    
    async getPositions() {
        const res = await fetch('/api/positions');
        return res.json();
    },
    
    async getTrades() {
        const res = await fetch('/api/trades');
        return res.json();
    },
    
    async getOpportunities() {
        const res = await fetch('/api/opportunities');
        return res.json();
    },
    
    async reset() {
        const res = await fetch('/api/reset', { method: 'POST' });
        return res.json();
    }
};

function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

function formatPercent(value) {
    return `${value.toFixed(1)}%`;
}

function formatTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function truncateText(text, maxLength = 50) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

async function updateStats() {
    try {
        const data = await API.getStats();
        const stats = data.stats;
        
        document.getElementById('balance').textContent = formatCurrency(stats.current_balance);
        document.getElementById('profit').textContent = formatCurrency(stats.total_profit);
        document.getElementById('positions').textContent = stats.open_positions;
        document.getElementById('opportunities').textContent = data.detector_stats.opportunities_found;
        
        document.getElementById('scan-count').textContent = data.scan_count;
        document.getElementById('last-scan').textContent = formatTime(data.last_scan);
        
        const dot = document.getElementById('scanner-dot');
        const text = document.getElementById('scanner-text');
        
        if (data.scan_count > 0) {
            dot.classList.add('active');
            text.textContent = 'Scanner Active';
        }
    } catch (err) {
        console.error('Failed to update stats:', err);
    }
}

async function updateOpportunities() {
    try {
        const data = await API.getOpportunities();
        const tbody = document.getElementById('opportunities-body');
        
        if (data.opportunities.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty">No opportunities detected yet...</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.opportunities.reverse().map(opp => `
            <tr>
                <td>${truncateText(opp.market_question)}</td>
                <td class="price-yes">$${opp.yes_price.toFixed(3)}</td>
                <td class="price-no">$${opp.no_price.toFixed(3)}</td>
                <td>$${opp.combined_cost.toFixed(3)}</td>
                <td class="profit">+$${opp.profit_per_share.toFixed(3)} (${opp.profit_percentage.toFixed(1)}%)</td>
                <td>${formatTime(opp.detected_at)}</td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Failed to update opportunities:', err);
    }
}

async function updatePositions() {
    try {
        const data = await API.getPositions();
        const tbody = document.getElementById('positions-body');
        
        if (data.positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty">No open positions...</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.positions.map(pos => `
            <tr>
                <td>${truncateText(pos.market_question)}</td>
                <td>${pos.yes_shares.toFixed(2)}</td>
                <td>${formatCurrency(pos.total_cost)}</td>
                <td class="profit">+${formatCurrency(pos.expected_profit)}</td>
                <td>${formatTime(pos.opened_at)}</td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Failed to update positions:', err);
    }
}

async function updateTrades() {
    try {
        const data = await API.getTrades();
        const tbody = document.getElementById('trades-body');
        
        if (data.trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty">No trades yet...</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.trades.map(trade => `
            <tr>
                <td>${truncateText(trade.market_question)}</td>
                <td>${trade.side.toUpperCase()}</td>
                <td class="${trade.outcome === 'Yes' ? 'price-yes' : 'price-no'}">${trade.outcome}</td>
                <td>${trade.shares.toFixed(2)}</td>
                <td>$${trade.price.toFixed(3)}</td>
                <td>${formatCurrency(trade.cost)}</td>
                <td>${formatTime(trade.timestamp)}</td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Failed to update trades:', err);
    }
}

async function refreshAll() {
    await Promise.all([
        updateStats(),
        updateOpportunities(),
        updatePositions(),
        updateTrades()
    ]);
}

// Reset button handler
document.getElementById('reset-btn').addEventListener('click', async () => {
    if (confirm('Are you sure you want to reset the paper trader? This will clear all positions and trades.')) {
        await API.reset();
        await refreshAll();
    }
});

// Initial load and auto-refresh
refreshAll();
setInterval(refreshAll, 2000);
