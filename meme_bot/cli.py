import asyncio
from argparse import ArgumentParser
from . import helper

def init_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="Meme Coin Bot",
        description="Application for solana meme coin bot",
        epilog="copyright @11vector"
    )

    subparsers = parser.add_subparsers(title="COMMANDS", required=True)

    """
    RPC COMMANDS
    """
    # rpc
    rpc_parser = subparsers.add_parser('rpc', help="rpc interaction")
    rpc_parser.set_defaults(async_=True)
    rpc_sub_parser = rpc_parser.add_subparsers(title="RPC COMMANDS")
    
    # rpc connected
    rpc_sub_parser.add_parser("connected")\
        .set_defaults(action=helper.rpc.connected)
    
    # rpc balance
    rpc_balance_parser = rpc_sub_parser.add_parser("balance")
    rpc_balance_parser.add_argument("acct_pk_sk", metavar="pub-srt-key")
    rpc_balance_parser.add_argument("--secret", dest='is_secret', action="store_true")
    rpc_balance_parser.add_argument("--sol", dest='format_sol', action="store_true")
    rpc_balance_parser.set_defaults(action=helper.rpc.get_balance)

    
    # rpc airdrop
    rpc_airdrop_parser = rpc_sub_parser.add_parser("airdrop")
    rpc_airdrop_parser.add_argument("acct_pk", metavar="pubKey")
    rpc_airdrop_parser.add_argument("amount", nargs='?',type=int, default=1,)
    rpc_airdrop_parser.add_argument("--sol", dest='format_sol', action="store_true")
    rpc_airdrop_parser.set_defaults(action=helper.rpc.airdrop)

    # rpc transfer
    rpc_transfer_parser = rpc_sub_parser.add_parser("transfer")
    rpc_transfer_parser.add_argument("--src", dest="src_sk", metavar="srcSecretKey")
    rpc_transfer_parser.add_argument('--dest', dest="dest_pk", metavar="destPubKey")
    rpc_transfer_parser.add_argument("--amount", type=int)
    rpc_transfer_parser.add_argument("--sol", dest='format_sol', action="store_true")
    rpc_transfer_parser.set_defaults(action=helper.rpc.transfer_sol)
    
    """
    ACCOUNT COMMANDS
    """
    # account
    acct_sub_parser = subparsers.add_parser('account', help="account operation")\
                        .add_subparsers(title="ACCOUNT COMMANDS")

    # account new
    acct_sub_parser.add_parser("new")\
        .set_defaults(action=helper.account.generate_keypair)
    
    # account address
    acct_addr_parser = acct_sub_parser.add_parser("address")
    acct_addr_parser.add_argument("acct_sk", metavar="srcSecretKey")
    acct_addr_parser.set_defaults(action=helper.account.get_address)
    
    # account oncurve
    acct_addr_parser = acct_sub_parser.add_parser("oncurve")
    acct_addr_parser.add_argument("acct_pk", metavar="pubKey")
    acct_addr_parser.set_defaults(action=helper.account.check_pda)
    
    """
    TOKEN COMMANDS
    """
    # mint
    mint_sub_parser = subparsers.add_parser('mint', help="mint operation")\
                        .add_subparsers(title="MINT COMMANDS")

    # mint new
    mint_new_parser = mint_sub_parser.add_parser("new")
    mint_new_parser.add_argument('--payer', dest="payer_sk", required=True)
    mint_new_parser.add_argument('--decimals', type=int, default=5)
    mint_new_parser.add_argument('--supply', type=int, default=100)
    mint_new_parser.set_defaults(action=helper.token.new_mint, async_=True)
    
    # mint account
    mint_acct_parser = mint_sub_parser.add_parser("account")
    mint_acct_parser.add_argument('--owner', dest="user_pk", required=True)
    mint_acct_parser.add_argument('--mint', dest="mint_pk", required=True)
    mint_acct_parser.set_defaults(action=helper.token.get_token_account)

    # mint balance
    mint_acct_parser = mint_sub_parser.add_parser("balance")
    mint_acct_parser.add_argument('--owner', dest="user_ata", required=True)
    mint_acct_parser.add_argument("--format", action="store_true")
    mint_acct_parser.set_defaults(action=helper.token.get_token_account_balance, async_=True)

    # mint transfer 
    mint_transfer_parser = mint_sub_parser.add_parser("transfer")
    mint_transfer_parser.add_argument('--src', dest="src_sk", metavar="srcSecretKey")
    mint_transfer_parser.add_argument('--dest', dest="dest_pk", metavar="destPubKey")
    mint_transfer_parser.add_argument('--mint', dest="mint_pk", required=True)
    mint_transfer_parser.add_argument("--amount", type=int)
    mint_transfer_parser.add_argument("--format", action="store_true")
    mint_transfer_parser.set_defaults(action=helper.token.transfer_token, async_=True)

    # mint drop
    mint_new_parser = mint_sub_parser.add_parser("drop")
    mint_new_parser.add_argument('--src', dest="src_sk", metavar="srcSecretKey")
    mint_new_parser.add_argument('--mint', dest="mint_pk", required=True)
    mint_new_parser.add_argument("--amount", type=int)
    mint_new_parser.add_argument("--format", action="store_true")
    mint_new_parser.set_defaults(action=helper.token.mint_drop, async_=True)

    return parser

def execute():
    parser = init_parser()
    options = vars(parser.parse_args())
    action = options.pop('action')
    is_async = options.pop("async_", False)
    
    if action:
        task = action(**options)
        if is_async:
            asyncio.run(task)