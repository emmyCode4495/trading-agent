"""
Tempo payments adapter. Tempo is a standard EVM chain (Reth-based), so
web3.py talks to it like any other EVM network — no special SDK required for
the basic transfer/balance operations this system needs. TIP-20 tokens
(Tempo's stablecoin standard) expose the same transfer/balanceOf/decimals
interface as ERC-20, so a minimal standard ABI is enough.

Verified network details (docs.tempo.xyz, checked while building this —
not assumed):
  Mainnet          chain ID 4217   https://rpc.tempo.xyz
  Testnet (Moderato) chain ID 42431  https://rpc.moderato.tempo.xyz
  pathUSD (first predeployed stablecoin): 0x20c0000000000000000000000000000000000000
    — this address comes from Tempo's predeployed-contracts page and should
    be the same on both networks (deterministic deployment), but confirm on
    https://explore.testnet.tempo.xyz before trusting it with real funds.

Tempo has NO native gas token — fees are paid in the TIP-20 stablecoin
itself. Wallet software may show a placeholder "ETH" balance; ignore it.

requirements pin: web3==6.20.3 (deliberately not the latest 8.x — see
requirements.txt comment; 8.x's eth-account floor conflicts with
hyperliquid-python-sdk's ceiling, and pinning here keeps both installable
in one environment).
"""
import logging

from eth_account import Account
from web3 import Web3

from app.config import settings

logger = logging.getLogger(__name__)

# Minimal ERC-20-compatible ABI — TIP-20 tokens implement this same interface.
_TIP20_ABI = [
    {"constant": True, "inputs": [{"name": "account", "type": "address"}], "name": "balanceOf",
     "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "from", "type": "address"},
        {"indexed": True, "name": "to", "type": "address"},
        {"indexed": False, "name": "value", "type": "uint256"},
    ], "name": "Transfer", "type": "event"},
]


class TempoError(Exception):
    pass


def _rpc_url() -> str:
    return settings.tempo_rpc_url_testnet if settings.tempo_env == "testnet" else settings.tempo_rpc_url_mainnet


def get_web3() -> Web3:
    w3 = Web3(Web3.HTTPProvider(_rpc_url()))
    if not w3.is_connected():
        raise TempoError(f"Could not reach Tempo RPC at {_rpc_url()}")
    return w3


def _token_contract(w3: Web3):
    return w3.eth.contract(address=Web3.to_checksum_address(settings.tempo_stablecoin_address), abi=_TIP20_ABI)


def get_stablecoin_balance(address: str) -> float:
    """Balance in whole-token units (e.g. 20.0 for 20 pathUSD), not base units."""
    w3 = get_web3()
    contract = _token_contract(w3)
    raw = contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
    return raw / (10 ** settings.tempo_stablecoin_decimals)


def send_stablecoin_payment(to_address: str, amount_usd: float) -> str:
    """
    Sends `amount_usd` of the configured TIP-20 stablecoin from the operator
    wallet to `to_address`. Returns the transaction hash. Used both for
    charging a subscriber's pre-authorized transfer flow (in the simplest
    hackathon version, the subscriber sends to the operator directly instead
    — see subscriptions.py) and for sending payouts.
    """
    if not settings.tempo_operator_private_key:
        raise TempoError(
            "TEMPO_OPERATOR_PRIVATE_KEY is not set. Get a wallet + testnet pathUSD from "
            "the faucet at https://tempo.xyz/developers/docs/quickstart/faucet, then set it in .env."
        )
    w3 = get_web3()
    account = Account.from_key(settings.tempo_operator_private_key)
    contract = _token_contract(w3)
    amount_base_units = int(round(amount_usd * (10 ** settings.tempo_stablecoin_decimals)))

    tx = contract.functions.transfer(Web3.to_checksum_address(to_address), amount_base_units).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": w3.eth.chain_id,
        # Tempo has no native gas token; fees are paid in the TIP-20 token
        # itself. gas/gasPrice below still get estimated in the chain's fee
        # units by the node — no separate native-gas top-up needed.
    })
    signed = account.sign_transaction(tx)
    # NOTE: web3==6.20.3 (pinned — see requirements.txt) names this
    # `rawTransaction`; it's `raw_transaction` only from web3 7.x onward. If
    # you ever upgrade web3 independently of this pin, this line breaks.
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    logger.info("Sent %.2f stablecoin to %s: %s", amount_usd, to_address, tx_hash.hex())
    return tx_hash.hex()


def verify_incoming_payment(tx_hash: str, expected_to: str, expected_min_amount_usd: float) -> bool:
    """
    Confirms a transaction actually paid `expected_min_amount_usd` (or more)
    of the configured stablecoin to `expected_to`. This is the check
    subscriptions.py runs before marking a subscriber active — never trust a
    client-submitted "I paid" claim without checking the chain.
    """
    w3 = get_web3()
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    if receipt is None or receipt.get("status") != 1:
        return False

    contract = _token_contract(w3)
    transfer_topic = w3.keccak(text="Transfer(address,address,uint256)").hex()
    for log in receipt["logs"]:
        if log["address"].lower() != settings.tempo_stablecoin_address.lower():
            continue
        if log["topics"][0].hex() != transfer_topic:
            continue
        decoded = contract.events.Transfer().process_log(log)
        to_addr = decoded["args"]["to"]
        amount = decoded["args"]["value"] / (10 ** settings.tempo_stablecoin_decimals)
        if to_addr.lower() == expected_to.lower() and amount >= expected_min_amount_usd:
            return True
    return False
