#
#   File:   listener.py
#   Author: Matteo Loporchio
#
#   This script contains an experimental event listener for the XCQA-bot.
#
#   The listener simulates a node of the target chain C2: the node listens
#   for requests, submitted by C1 users with the Bridge smart contract,
#   and queries the Ethereum mainnet to fetch the desired information.
#   By invoking the verify() method, the request response,
#   along with the corresponding proof, is sent back to the contract.
#   The contract, in turn, will verify the correctness of the proof
#   and notify nodes of C1.
#
#   NOTICE: Queries to the Ethereum mainnet are performed using
#   the Ethereum JSON-RPC API. Therefore, a token for accessing the API
#   should be provided in the configuration file (i.e., `config.dat`).
#

import asyncio
import configparser
import json
import sys
from web3 import Web3
from web3._utils.encoding import pad_bytes

config = configparser.ConfigParser()
config.read('config.dat')
hostname = config['general']['hostname']
port = int(config['general']['port'])
contractPath = config['general']['contractPath']
contractAddress = config['general']['contractAddress']
token = config['auth']['token'] # Infura token
endpointUrl = 'https://mainnet.infura.io/v3/{}'.format(token)
chainAddress = 'http://{}:{}'.format(hostname, port)

web3 = Web3(Web3.HTTPProvider(chainAddress))
web3.eth.defaultAccount = web3.eth.accounts[0]
with open(contractPath) as file:
    contractJson = json.load(file)
    contractAbi = contractJson['abi']
contract = web3.eth.contract(address=contractAddress, abi=contractAbi)

def handle_event(event):
    requestId = event['args']['requestId']
    account = event['args']['account']
    key = event['args']['key']
    blockId = event['args']['blockId']
    # Query the Ethereum mainnet to retrieve the desired variable.
    infura = Web3(Web3.HTTPProvider(endpointUrl))
    block = infura.eth.get_block(blockId)
    proof = infura.eth.get_proof(account, [key], blockId)
    # Construct the state proof.
    stateProof = [
        block.stateRoot,
        account,
        proof.accountProof,
        proof.storageHash,
        pad_bytes(b'\x00', 32, proof.storageProof[0].key),
        proof.storageProof[0].value,
        proof.storageProof[0].proof
    ]
    # Call the verification method on the blockchain.
    txn_hash = contract.functions.verify(requestId, stateProof).transact()
    web3.eth.wait_for_transaction_receipt(txn_hash)
    # Extract the value from the proof.
    value = (proof['storageProof'][0]['value']).hex()
    print(f'Request {requestId} has been served (value: {value}).')

async def log_loop(event_filter, poll_interval):
    while True:
        for e in event_filter.get_new_entries():
            handle_event(e)
        await asyncio.sleep(poll_interval)

def main():
    print('Listener has started!\nChain\t: {}\nContract: {}\nAddress\t: {}\nToken\t: {}'.format(
        chainAddress, contractPath, contractAddress, token))
    event_filter = contract.events.RequestLogged.createFilter(fromBlock='latest')
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(asyncio.gather(log_loop(event_filter, 2)))
    finally:
        loop.close()

if __name__ == "__main__":
    main()
