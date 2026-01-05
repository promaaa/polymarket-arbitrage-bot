use futures_util::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Deserializer, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;

const GAMMA_API: &str = "https://gamma-api.polymarket.com/markets";
const MIN_PROFIT_THRESHOLD: f64 = 0.01;
const MIN_VOLUME: f64 = 10000.0;

// Helper to deserialize string or number as f64
fn de_string_or_number<'de, D>(deserializer: D) -> Result<Option<f64>, D::Error>
where
    D: Deserializer<'de>,
{
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum StringOrNumber {
        String(String),
        Number(f64),
        Null,
    }

    match StringOrNumber::deserialize(deserializer)? {
        StringOrNumber::String(s) => Ok(s.parse().ok()),
        StringOrNumber::Number(n) => Ok(Some(n)),
        StringOrNumber::Null => Ok(None),
    }
}

#[derive(Debug, Clone, Serialize)]
struct Market {
    id: String,
    question: String,
    volume: f64,
    liquidity: f64,
    yes_price: f64,
    no_price: f64,
}

#[derive(Debug, Clone, Serialize)]
struct Opportunity {
    market_id: String,
    question: String,
    yes_price: f64,
    no_price: f64,
    combined_cost: f64,
    profit: f64,
    profit_pct: f64,
    timestamp_ms: u128,
}

#[derive(Debug, Deserialize)]
struct GammaMarket {
    id: Option<String>,
    question: Option<String>,
    #[serde(rename = "volumeNum", default, deserialize_with = "de_string_or_number")]
    volume_num: Option<f64>,
    #[serde(default, deserialize_with = "de_string_or_number")]
    liquidity: Option<f64>,
    #[serde(rename = "outcomePrices")]
    outcome_prices: Option<String>,
}

type MarketCache = Arc<RwLock<HashMap<String, Market>>>;

async fn fetch_markets(client: &Client) -> Result<Vec<Market>, Box<dyn std::error::Error + Send + Sync>> {
    let start = Instant::now();
    
    let resp = client
        .get(GAMMA_API)
        .query(&[("active", "true"), ("closed", "false"), ("limit", "200")])
        .send()
        .await?;
    
    let text = resp.text().await?;
    let markets: Vec<GammaMarket> = serde_json::from_str(&text)?;
    let elapsed = start.elapsed();
    
    let parsed: Vec<Market> = markets
        .into_iter()
        .filter_map(|m| {
            let id = m.id?;
            let question = m.question.unwrap_or_default();
            let volume = m.volume_num.unwrap_or(0.0);
            let liquidity = m.liquidity.unwrap_or(0.0);
            
            // Parse outcome prices - it's a JSON array of strings like ["0.0045", "0.9955"]
            let prices: Vec<f64> = m.outcome_prices
                .and_then(|p| {
                    // First try parsing as array of strings
                    let parsed: Result<Vec<String>, _> = serde_json::from_str(&p);
                    if let Ok(v) = parsed {
                        return Some(v.iter().filter_map(|s| s.parse().ok()).collect());
                    }
                    // Fallback: try parsing as array of numbers
                    let parsed: Result<Vec<f64>, _> = serde_json::from_str(&p);
                    parsed.ok()
                })
                .unwrap_or_default();
            
            if prices.len() >= 2 {
                Some(Market {
                    id,
                    question,
                    volume,
                    liquidity,
                    yes_price: prices[0],
                    no_price: prices[1],
                })
            } else {
                None
            }
        })
        .collect();
    
    println!("⚡ Fetched {} markets in {:?}", parsed.len(), elapsed);
    Ok(parsed)
}

fn detect_opportunities(markets: &[Market]) -> Vec<Opportunity> {
    let start = Instant::now();
    
    let mut opportunities: Vec<Opportunity> = markets
        .iter()
        .filter(|m| m.volume >= MIN_VOLUME)
        .filter_map(|m| {
            let combined = m.yes_price + m.no_price;
            let profit = 1.0 - combined;
            
            if profit >= MIN_PROFIT_THRESHOLD && m.yes_price > 0.0 && m.no_price > 0.0 && combined < 1.0 {
                let profit_pct = (profit / combined) * 100.0;
                Some(Opportunity {
                    market_id: m.id.clone(),
                    question: m.question.clone(),
                    yes_price: m.yes_price,
                    no_price: m.no_price,
                    combined_cost: combined,
                    profit,
                    profit_pct,
                    timestamp_ms: std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap()
                        .as_millis(),
                })
            } else {
                None
            }
        })
        .collect();
    
    // Sort by profit percentage descending
    opportunities.sort_by(|a, b| b.profit_pct.partial_cmp(&a.profit_pct).unwrap());
    
    let elapsed = start.elapsed();
    println!("⚡ Detected {} opportunities in {:?}", opportunities.len(), elapsed);
    
    opportunities
}

async fn scan_loop(client: Client, _cache: MarketCache) {
    let mut scan_count = 0u64;
    let mut total_fetch_time = Duration::ZERO;
    let mut total_detect_time = Duration::ZERO;
    
    loop {
        let fetch_start = Instant::now();
        
        match fetch_markets(&client).await {
            Ok(markets) => {
                let fetch_time = fetch_start.elapsed();
                total_fetch_time += fetch_time;
                
                let detect_start = Instant::now();
                let opportunities = detect_opportunities(&markets);
                let detect_time = detect_start.elapsed();
                total_detect_time += detect_time;
                
                scan_count += 1;
                
                // Print stats every scan
                println!("\n📊 Scan #{} | Fetch: {:?} | Detect: {:?} | Avg: {:?}",
                    scan_count,
                    fetch_time,
                    detect_time,
                    total_fetch_time / scan_count as u32
                );
                
                if !opportunities.is_empty() {
                    println!("\n🎯 Top {} Opportunities:", opportunities.len().min(5));
                    println!("{:<50} {:>8} {:>8} {:>8} {:>8}",
                        "Market", "YES", "NO", "Total", "Profit"
                    );
                    println!("{}", "-".repeat(86));
                    
                    for opp in opportunities.iter().take(5) {
                        let q = if opp.question.len() > 47 {
                            format!("{}...", &opp.question[..47])
                        } else {
                            opp.question.clone()
                        };
                        println!("{:<50} ${:>6.3} ${:>6.3} ${:>6.3} {:>6.1}%",
                            q,
                            opp.yes_price,
                            opp.no_price,
                            opp.combined_cost,
                            opp.profit_pct
                        );
                    }
                }
            }
            Err(e) => {
                eprintln!("❌ Error: {}", e);
            }
        }
        
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
}

#[tokio::main]
async fn main() {
    println!("🦀 Polymarket Rust Scanner - High Performance Mode");
    println!("================================================");
    println!("Min profit: {}%", MIN_PROFIT_THRESHOLD * 100.0);
    println!("Min volume: ${:.0}", MIN_VOLUME);
    println!();
    
    let client = Client::builder()
        .timeout(Duration::from_secs(10))
        .pool_max_idle_per_host(10)
        .build()
        .expect("Failed to create HTTP client");
    
    let cache: MarketCache = Arc::new(RwLock::new(HashMap::new()));
    
    println!("Starting scanner (polling every 2s)...\n");
    
    scan_loop(client, cache).await;
}
