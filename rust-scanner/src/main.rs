use futures_util::{SinkExt, StreamExt};
use reqwest::Client;
use serde::{Deserialize, Deserializer, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{RwLock, mpsc};
use tokio_tungstenite::{connect_async, tungstenite::protocol::Message};
use url::Url;

enum WsCommand {
    Subscribe(Vec<String>),
}

const GAMMA_API: &str = "https://gamma-api.polymarket.com/markets";
const WS_URL: &str = "wss://ws-subscriptions-clob.polymarket.com/ws/market";
const MIN_PROFIT_THRESHOLD: f64 = 0.002; // 0.2%
const MIN_VOLUME: f64 = 5000.0;
const PAGE_SIZE: usize = 100;
const MAX_PAGES: usize = 20; 

// --- Structs ---

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
    yes_token_id: String,
    no_token_id: String,
    best_ask_yes: Option<f64>,
    best_ask_no: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct Opportunity {
    market_id: String,
    #[serde(rename = "market_question")]
    question: String,
    yes_price: f64,
    no_price: f64,
    combined_cost: f64,
    #[serde(rename = "profit_per_share")]
    profit: f64,
    #[serde(rename = "profit_percentage")]
    profit_pct: f64,
    source: String,
    detected_at: String,
}

#[derive(Debug, Deserialize)]
struct GammaMarket {
    id: Option<String>,
    question: Option<String>,
    #[serde(rename = "volumeNum", default, deserialize_with = "de_string_or_number")]
    volume_num: Option<f64>,
    #[serde(default, deserialize_with = "de_string_or_number")]
    liquidity: Option<f64>,
    #[serde(rename = "clobTokenIds")]
    clob_token_ids: Option<String>,
}

#[derive(Debug, Deserialize)]
struct WsPriceUpdate {
    #[serde(rename = "type")]
    msg_type: String,
    token_id: Option<String>,
    price: Option<String>,
    side: Option<String>,
}

type MarketMap = Arc<RwLock<HashMap<String, Market>>>;
type TokenMap = Arc<RwLock<HashMap<String, String>>>; // TokenID -> MarketID

// --- Data Fetching ---

fn parse_market(m: GammaMarket) -> Option<Market> {
    let id = m.id?;
    let question = m.question.unwrap_or_default();
    let volume = m.volume_num.unwrap_or(0.0);
    let liquidity = m.liquidity.unwrap_or(0.0);
    let tokens: Vec<String> = m.clob_token_ids
        .and_then(|p| serde_json::from_str(&p).ok())
        .unwrap_or_default();
        
    if tokens.len() >= 2 {
        Some(Market {
            id,
            question,
            volume,
            liquidity,
            yes_token_id: tokens[0].clone(),
            no_token_id: tokens[1].clone(),
            best_ask_yes: None,
            best_ask_no: None,
        })
    } else {
        None
    }
}

async fn fetch_all_markets(client: &Client) -> Result<Vec<Market>, Box<dyn std::error::Error + Send + Sync>> {
    let start = Instant::now();
    let mut all_markets = Vec::new();
    let mut handles = Vec::new();
    
    for page in 0..MAX_PAGES {
        let client = client.clone();
        let offset = page * PAGE_SIZE;
        handles.push(tokio::spawn(async move {
            let resp = client.get(GAMMA_API)
                .query(&[("active", "true"), ("closed", "false"), ("limit", &PAGE_SIZE.to_string()), ("offset", &offset.to_string())])
                .send().await?;
            let text = resp.text().await?;
            let markets: Vec<GammaMarket> = serde_json::from_str(&text)?;
            Ok::<Vec<Market>, Box<dyn std::error::Error + Send + Sync>>(
                markets.into_iter().filter_map(parse_market).collect()
            )
        }));
    }
    
    for handle in handles {
        if let Ok(Ok(markets)) = handle.await {
            all_markets.extend(markets);
        }
    }
    
    println!("⚡ Fetched {} markets in {:?}", all_markets.len(), start.elapsed());
    Ok(all_markets)
}

// --- Logic ---

mod execute;
mod mock_data;
use execute::Executor;

#[cfg(test)]
mod tests {
    use super::mock_data;

    #[test]
    fn test_mock_data_integrity() {
        assert!(mock_data::MOCK_MARKET_DATA.len() > 0);
        // Basic check to ensure data is compiled
        assert!(mock_data::MOCK_MARKET_DATA[0].price >= 0.0);
    }
}


// ... imports ...

// --- Data Fetching ---

// ...

// --- Logic ---

fn save_opportunities(ops: &[Opportunity]) {
    use std::io::Write;
    let data = serde_json::json!({
        "opportunities": ops,
        "last_updated": chrono::Utc::now().to_rfc3339(),
        "count": ops.len()
    });
    if let Ok(mut f) = std::fs::File::create("opportunities.json") {
        let _ = f.write_all(data.to_string().as_bytes());
    }
}

async fn handle_price_update(token_id: &str, price: f64, markets: &MarketMap, tokens: &TokenMap, executor: Option<&Arc<Executor>>) {
    let market_id = {
         let t_map = tokens.read().await;
         match t_map.get(token_id) {
             Some(mid) => mid.clone(),
             None => return,
         }
    };
    
    let (opp, yes_id, no_id) = {
        let mut m_map = markets.write().await;
        if let Some(market) = m_map.get_mut(&market_id) {
            if market.yes_token_id == token_id {
                market.best_ask_yes = Some(price);
            } else if market.no_token_id == token_id {
                market.best_ask_no = Some(price);
            }
            
            if let (Some(yes), Some(no)) = (market.best_ask_yes, market.best_ask_no) {
                let cost = yes + no;
                if cost < 1.0 && (1.0 - cost) >= MIN_PROFIT_THRESHOLD {
                   let profit = 1.0 - cost;
                   let opp = Opportunity {
                       market_id: market.id.clone(),
                       question: market.question.clone(),
                       yes_price: yes,
                       no_price: no,
                       combined_cost: cost,
                       profit,
                       profit_pct: (profit / cost) * 100.0,
                       source: "WS".to_string(),
                       detected_at: chrono::Utc::now().to_rfc3339(),
                   };
                   (Some(opp), market.yes_token_id.clone(), market.no_token_id.clone())
                } else { (None, String::new(), String::new()) }
            } else { (None, String::new(), String::new()) }
        } else { (None, String::new(), String::new()) }
    };
    
    if let Some(o) = opp {
        println!("🚀 ARB: {:.1}% on '{}' (${:.3}/${:.3})", o.profit_pct, o.question, o.yes_price, o.no_price);
        
        // EXECUTE
        if let Some(exec) = executor {
            println!("💸 Executing Trade...");
            // Size: Fixed size from ENV or const. Let's use 10 USD (small).
            // Example: 10 USDC / price = shares.
            let size_usdc = 10.0;
            let size_yes = size_usdc / o.yes_price;
            let size_no = size_usdc / o.no_price;
            
            // Execute in parallel
            let exec_yes = exec.clone();
            let exec_no = exec.clone();
            let y_id = yes_id.clone();
            let n_id = no_id.clone();
            let y_p = o.yes_price;
            let n_p = o.no_price;
            
            tokio::spawn(async move {
                let r1 = exec_yes.execute_buy(&y_id, y_p, size_yes);
                let r2 = exec_no.execute_buy(&n_id, n_p, size_no);
                let (res_yes, res_no) = tokio::join!(r1, r2);
                
                match res_yes {
                    Ok(tx) => println!("✅ YES Order Sent: {:?}", tx),
                    Err(e) => eprintln!("❌ YES Failed: {}", e),
                }
                match res_no {
                    Ok(tx) => println!("✅ NO Order Sent: {:?}", tx),
                    Err(e) => eprintln!("❌ NO Failed: {}", e),
                }
            });
        }
    }
}

// --- Main ---

async fn market_refresher(
    client: Client,
    market_map: MarketMap,
    token_map: TokenMap,
    tx: mpsc::Sender<WsCommand>
) {
    loop {
        tokio::time::sleep(Duration::from_secs(60)).await;
        println!("🔄 Refreshing Markets...");
        if let Ok(mut markets) = fetch_all_markets(&client).await {
            markets.retain(|m| m.volume >= MIN_VOLUME);
            markets.sort_by(|a, b| b.volume.partial_cmp(&a.volume).unwrap());
            markets.truncate(50);
            
            let mut new_tokens = Vec::new();
            {
                let mut m_lock = market_map.write().await;
                let mut t_lock = token_map.write().await;
                
                for m in markets {
                    if !m_lock.contains_key(&m.id) {
                        println!("🆕 New Market Found: {}", m.question);
                        m_lock.insert(m.id.clone(), m.clone());
                        t_lock.insert(m.yes_token_id.clone(), m.id.clone());
                        t_lock.insert(m.no_token_id.clone(), m.id.clone());
                        new_tokens.push(m.yes_token_id);
                        new_tokens.push(m.no_token_id);
                    }
                }
            }
            if !new_tokens.is_empty() {
                if let Err(e) = tx.send(WsCommand::Subscribe(new_tokens)).await {
                    eprintln!("❌ Failed to send subscribe command: {}", e);
                }
            }
        }
    }
}

#[tokio::main]
async fn main() {
    dotenv::dotenv().ok();
    println!("🦀 Polymarket Rust Scanner - WebSocket Speed Mode");
    
    // Init Executor
    let executor = if let (Ok(pk), Ok(proxy)) = (std::env::var("PRIVATE_KEY"), std::env::var("POLY_PROXY_ADDRESS")) {
        println!("🔐 Executor Initialized (Proxy: {})", proxy);
        Some(Arc::new(Executor::new(&pk, &proxy)))
    } else {
        println!("⚠️ No Private Key found. Read-only mode.");
        None
    };



    let client = Client::builder().build().unwrap();
    let mut markets = fetch_all_markets(&client).await.unwrap_or_default();
    
    // Filter & Sort
    markets.retain(|m| m.volume >= MIN_VOLUME);
    markets.sort_by(|a, b| b.volume.partial_cmp(&a.volume).unwrap());
    markets.truncate(50); // Top 50
    
    println!("Monitoring Top {} Markets via WebSocket", markets.len());
    
    let market_map: MarketMap = Arc::new(RwLock::new(HashMap::new()));
    let token_map: TokenMap = Arc::new(RwLock::new(HashMap::new()));
    
    // Create Channel for dynamic subscriptions
    let (tx, mut rx) = mpsc::channel(32);
    
    // Spawn Refresher
    let client_clone = client.clone();
    let mm = market_map.clone();
    let tm = token_map.clone();
    let tx_clone = tx.clone();
    tokio::spawn(market_refresher(client_clone, mm, tm, tx_clone));
    
    {
        let mut m_lock = market_map.write().await;
        let mut t_lock = token_map.write().await;
        for m in &markets {
            m_lock.insert(m.id.clone(), m.clone());
            t_lock.insert(m.yes_token_id.clone(), m.id.clone());
            t_lock.insert(m.no_token_id.clone(), m.id.clone());
        }
    }
    
    // Background Task: Periodic JSON Save (Snapshot)
    let market_map_clone = market_map.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(1)).await;
            let mut ops = Vec::new();
            {
                let map = market_map_clone.read().await;
                for m in map.values() {
                    if let (Some(yes), Some(no)) = (m.best_ask_yes, m.best_ask_no) {
                        let cost = yes + no;
                        if cost < 1.0 {
                            let profit = 1.0 - cost;
                            if profit >= MIN_PROFIT_THRESHOLD {
                                ops.push(Opportunity {
                                    market_id: m.id.clone(),
                                    question: m.question.clone(),
                                    yes_price: yes,
                                    no_price: no,
                                    combined_cost: cost,
                                    profit,
                                    profit_pct: (profit / cost) * 100.0,
                                    source: "WS".to_string(),
                                    detected_at: chrono::Utc::now().to_rfc3339(),
                                });
                            }
                        }
                    }
                }
            }
            ops.sort_by(|a, b| b.profit_pct.partial_cmp(&a.profit_pct).unwrap());
            save_opportunities(&ops);
        }
    });

    // WebSocket Loop
    let url = Url::parse(WS_URL).unwrap();
    loop {
        println!("🔌 Connecting to WebSocket...");
        match connect_async(url.clone()).await {
            Ok((ws_stream, _)) => {
                println!("✅ Connected!");
                let (mut write, mut read) = ws_stream.split();
                
                // Subscribe
                {
                    let tokens = token_map.read().await;
                    for token_id in tokens.keys() {
                        let msg = serde_json::json!({
                            "type": "subscribe",
                            "channel": "price",
                            "token_id": token_id
                        });
                        write.send(Message::Text(msg.to_string())).await.ok(); 
                    }
                    println!("📡 Subscribed to {} tokens", tokens.len());
                }
                

                
                loop {
                    tokio::select! {
                        Some(cmd) = rx.recv() => {
                            match cmd {
                                WsCommand::Subscribe(ids) => {
                                    for token_id in ids {
                                        let msg = serde_json::json!({
                                            "type": "subscribe",
                                            "channel": "price",
                                            "token_id": token_id
                                        });
                                        if let Err(e) = write.send(Message::Text(msg.to_string())).await {
                                            eprintln!("❌ Failed to send subscribe: {}", e);
                                        }
                                    }
                                    println!("📡 Dynamically subscribed to new tokens");
                                }
                            }
                        }
                        
                        maybe_msg = read.next() => {
                            match maybe_msg {
                                Some(Ok(Message::Text(text))) => {
                                   if let Ok(update) = serde_json::from_str::<WsPriceUpdate>(&text) {
                                       if update.msg_type == "price" {
                                           if let (Some(tid), Some(p_str)) = (update.token_id, update.price) {
                                               if update.side.as_deref() == Some("sell") {
                                                    if let Ok(price) = p_str.parse::<f64>() {
                                                        handle_price_update(&tid, price, &market_map, &token_map, executor.as_ref()).await;
                                                    }
                                               }
                                           }
                                       }
                                   }
                                }
                                Some(Ok(Message::Close(_))) => break,
                                Some(Err(_)) => break,
                                None => break,
                                _ => {}
                            }
                        }
                    }
                }
            }
            Err(e) => {
                eprintln!("WS Connection failed: {}", e);
                tokio::time::sleep(Duration::from_secs(5)).await;
            }
        }
    }
}


