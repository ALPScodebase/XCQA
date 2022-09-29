#
#   File:   bot.py
#   Author: Matteo Loporchio
#
#   This Python script contains a Telegram bot for interacting
#   with the Bridge XCQA smart contract.
#
#   The bot allows users to interact with the Bridge smart contract
#   by submitting new requests and reading the corresponding replies.
#
#   To run this script, just type:
#
#       python3 bot.py
#
#   NOTICE: Before running the script, make sure that the current
#   directory contains the configuration file named 'config.dat'.
#   The file should include your token for interacting with the Telegram API.
#   You can obtain a token for running the bot through Telegram's BotFather
#   (https://telegram.me/BotFather).

import asyncio
import configparser
import json
import queue
import threading
import time
from datetime import datetime
from web3 import Web3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler

# Read and parse the configuration file.
config = configparser.ConfigParser()
config.read('config.dat')
hostname = config['general']['hostname']
port = int(config['general']['port'])
contractPath = config['general']['contractPath']
contractAddress = config['general']['contractAddress']
botToken = config['auth']['botToken']
chainAddress = 'http://{}:{}'.format(hostname, port)

# Fetch a reference to the deployed Bridge smart contract.
web3 = Web3(Web3.HTTPProvider(chainAddress))
web3.eth.defaultAccount = web3.eth.accounts[0]
with open(contractPath) as file:
    contractJson = json.load(file)
    contractAbi = contractJson['abi']
contract = web3.eth.contract(address=contractAddress, abi=contractAbi)

# This utility function is called after a request has been submitted.
# The bot uses it to listen for incoming 'RequestServed' events.
def listen(eventFilter):
    received = False
    entries = None
    # Periodically check if a new 'RequestServed' event has been triggered.
    # A check is performed every two seconds.
    while not received:
        entries = eventFilter.get_new_entries()
        if (len(entries) > 0):
            received = True
        else:
            time.sleep(2)
    return entries[0]

# Says 'hello' to the user.
async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}!')

# Displays a 'help' message with a list of all available commands.
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    helpMessage = (
        "These are the available commands:\n" +
        "/hello: says hello to the user\n" +
        "/counter: returns the number of issued requests\n" +
        "/pending: returns the number of pending requests\n" +
        "/served: returns the number of served requests\n" +
        "/request <account> <key> <blockId>: triggers a request " +
        "for reading the variable <key> located inside the contract " +
        "with address <account> at block <blockId>.\n" +
        "/check <requestId>: checks the status of a given request."
    )
    await update.message.reply_text(helpMessage)

# Returns the total number of requests.
async def counter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = contract.functions.getTotal().call()
    await update.message.reply_text(f'There are currently {message} submitted requests.')

# Returns the number of currently pending requests.
async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = contract.functions.getPending().call()
    await update.message.reply_text(f'There are currently {message} pending requests.')

# Returns the number of served requests.
async def served(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = contract.functions.getServed().call()
    await update.message.reply_text(f'There are currently {message} served requests.')

# Creates and submits a new request.
async def request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    account = context.args[0]
    key = int(context.args[1])
    blockId = int(context.args[2])
    # Call the request() method in the contract to create a new request.
    txn_hash = contract.functions.request(account, key, blockId, 0, 0).transact()
    txn_receipt = web3.eth.wait_for_transaction_receipt(txn_hash)
    requestId = int(contract.functions.getTotal().call()) - 1
    await update.message.reply_text(f'Request created (id: {requestId}).\nAccount: {account}\nKey: {key}\nBlock Id: {blockId}\n')
    # Listen for the reply and send the result.
    eventFilter = contract.events.RequestServed.createFilter(fromBlock='latest', argument_filters={'requestId': requestId})
    event = listen(eventFilter)
    requestId = event['args']['requestId']
    reply = '0x' + (event['args']['reply']).hex()
    #reply = (event['args']['reply']).hex()
    await update.message.reply_text(f'Request served (id: {requestId}).\nReply: {reply}\n')

# Returns the status of a given request.
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    requestId = int(context.args[0])
    try:
        # Invoke the getRequest() method in the contract to get the request.
        msg = contract.functions.getRequest(requestId).call()
        date = datetime.fromtimestamp(msg[3])
        resp = '0x' + msg[7].hex()
        await update.message.reply_text(
        f'Request Id: {requestId}\nAddress: {msg[0]}\nKey: {msg[1]}\nBlock: {msg[2]}\nDate: {date}\nServed: {msg[6]}\nResponse: {resp}\n')
    except:
        # If the getRequest() method fails, display an error message.
        await update.message.reply_text(f'Sorry, I couldn\'t find any request with id={requestId}.')

# Handler for unknown commands.
# def unknown(bot, update):
#     bot.sendMessage(chat_id=update.message.chat_id,
#     text='Sorry, I didn\'t understand that command.')

# Bot initialization. During this phase, we simply register handlers
# for all available commands.
print('Bot has started!\nChain\t: {}\nContract: {}\nAddress\t: {}\nToken\t: {}'.format(
    chainAddress, contractPath, contractAddress, botToken))
app = ApplicationBuilder().token(botToken).build()
app.add_handler(CommandHandler("hello", hello))
app.add_handler(CommandHandler("counter", counter))
app.add_handler(CommandHandler("pending", pending))
app.add_handler(CommandHandler("served", served))
app.add_handler(CommandHandler("request", request))
app.add_handler(CommandHandler("check", check))
app.add_handler(CommandHandler("help", help))
#app.add_handler(MessageHandler(Filters.command, unknown))

print('Handlers added successfully!')
app.run_polling()
