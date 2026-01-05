use ethers::prelude::*;
use rand::Rng;
use reqwest::Client;
use serde::Serialize;
use std::env;
use std::str::FromStr;
use std::time::{SystemTime, UNIX_EPOCH};

const CLOB_API_URL: &str = "https://clob.polymarket.com/order";
const CHAIN_ID: u64 = 137;
const EXCHANGE: &str = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"; // CTF Exchange

#[derive(Eip712, EthAbiType, Clone, Debug)]
#[eip712(
    name = "Polymarket CTF Exchange",
    version = "1",
    chain_id = 137,
    verifying_contract = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
)]
pub struct Order {
    pub salt: U256,
    pub maker: Address,
    pub signer: Address,
    pub taker: Address,
    pub token_id: U256,
    pub maker_amount: U256,
    pub taker_amount: U256,
    pub expiration: U256,
    pub nonce: U256,
    pub fee_rate_bps: U256,
    pub side: u8,
    pub signature_type: u8,
}

#[derive(Serialize)]
struct OrderRequest {
    order: OrderJson,
    owner: String,
    signature: String,
    orderType: String, // "FOK"
}

#[derive(Serialize)]
struct OrderJson {
    salt: String,
    maker: String,
    signer: String,
    taker: String,
    tokenId: String,
    makerAmount: String,
    takerAmount: String,
    expiration: String,
    nonce: String,
    feeRateBps: String,
    side: u8,
    signatureType: u8,
}

pub struct Executor {
    wallet: LocalWallet,
    proxy_address: Address,
    client: Client,
}

impl Executor {
    pub fn new(private_key: &str, proxy: &str) -> Self {
        let wallet = LocalWallet::from_str(private_key).expect("Invalid PK").with_chain_id(CHAIN_ID);
        let proxy_address = Address::from_str(proxy).expect("Invalid Proxy");
        Self {
            wallet,
            proxy_address,
            client: Client::new(),
        }
    }

    pub async fn execute_buy(&self, token_id_str: &str, price: f64, size: f64) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        // Prepare Order
        let token_id = U256::from_dec_str(token_id_str)?;
        let nonce = U256::from(0); // For FOK? Or random? CLOB usually ignores nonce for FOK or random
        // Salt: Random
        let salt: U256 = U256::from(rand::thread_rng().gen::<u64>());
        
        // Amounts
        // Size = shares.
        // makerAmount (USDC) = size * price.
        // takerAmount (Shares) = size.
        // USDC has 6 decimals.
        // Polymarket tokens have ? Usually 6 or 18?
        // CTF tokens are 6 decimals usually? Wait.
        // "Binary markets ... usually 6 decimals for USDC, ? for Tokens".
        // Docs: "Collateral is USDC (6 decimals)". "Outcome tokens are 18 decimals"? No, 6.
        // Gamma API volume is in units.
        // Let's assume 6 decimals for all (1 USDC = 1,000,000).
        // WARNING: Precision matters.
        
        let decimals = 1_000_000.0;
        let maker_float = size * price * decimals;
        let taker_float = size * decimals;
        
        let maker_amount = U256::from(maker_float as u64);
        let taker_amount = U256::from(taker_float as u64);
        
        let order = Order {
            salt,
            maker: self.proxy_address,
            signer: self.wallet.address(),
            taker: Address::zero(), // Open order
            token_id,
            maker_amount,
            taker_amount,
            expiration: U256::from(0), // FOK (match or kill)
            nonce,
            fee_rate_bps: U256::from(0),
            side: 0, // Buy
            signature_type: 0, // EOA signature (if signer is EOA)
        };
        
        // Sign
        let signature = self.wallet.sign_typed_data(&order).await?;
        let sig_str = format!("0x{}", hex::encode(signature.to_vec()));
        
        // Setup Payload
        let payload = OrderRequest {
            order: OrderJson {
                salt: order.salt.to_string(),
                maker: format!("{:?}", order.maker),
                signer: format!("{:?}", order.signer),
                taker: "0x0000000000000000000000000000000000000000".to_string(),
                tokenId: order.token_id.to_string(),
                makerAmount: order.maker_amount.to_string(),
                takerAmount: order.taker_amount.to_string(),
                expiration: "0".to_string(),
                nonce: "0".to_string(),
                feeRateBps: "0".to_string(),
                side: 0,
                signatureType: 0,
            },
            owner: format!("{:?}", self.proxy_address), // Proxy is owner of funds
            signature: sig_str,
            orderType: "FOK".to_string(),
        };
        
        // Submit
        let resp = self.client.post(CLOB_API_URL)
            .json(&payload)
            .send()
            .await?;
            
        let text = resp.text().await?;
        Ok(text)
    }
}
