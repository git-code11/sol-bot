import asyncio
import inquirer
from . import SaleType, print_screen, utils, BotManager


def start():
    non_empty_validator = lambda _, x: len(x)>0
    questions = [
        inquirer.Text("target_addr", 
                      message="Enter target address", 
                      validate=non_empty_validator,
                      default="87esLg2WdmndkRjYrxNene4cXrGsSAeVyQxAG9tcRh1m"),
        inquirer.Text("amount", 
                      message="Enter amount in sol to purchase", 
                      validate=non_empty_validator, 
                      default=0.001),
        inquirer.Text("timeout", 
                      message="Enter the sale time interval from sales in seconds", 
                      validate=non_empty_validator, 
                      default=30),
        inquirer.Text("min_profit", 
                      message="Enter the profit amount for sales in dollars", 
                      validate=non_empty_validator, 
                      default=0.00001),
        inquirer.Text("poll_interval", 
                      message="Enter Polling Interval in seconds", 
                      validate=non_empty_validator, 
                      default=1*60),
        inquirer.Text("bot_secret", 
                      message="Enter Bot SecretKey", 
                      validate=non_empty_validator,
                      default="8e41ad5b7a6c5e9a7cee9d3b46a9c34bf2ac5efeb1fcfc9b62522c0d862ceb24"),
        inquirer.Checkbox(
            "sale_type",
            message="Select the meme coin sales strategy?",
            choices=[
                ("Timed Interval", SaleType.TIMER),
                ("Capped Amount", SaleType.CAPPED),
                ("Combined Strategy", SaleType.BOTH),
            ],
            default=[SaleType.BOTH]
        ),
    ]

    print_screen()
          
    data = inquirer.prompt(questions)
    # preprocess
    data['amount'] = utils.sol_to_lamport(float(data['amount']))
    data['timeout'] = int(data['timeout'])
    data['min_profit'] = float(data['min_profit'])
    data['sale_type'] = data['sale_type'][0]
    data['poll_interval'] = int(data['poll_interval'])

    manager = BotManager(
        target_addr=data['target_addr'],
        bot_secret=data['bot_secret'],
        amount=data['amount'],
        sale_type=data['sale_type'],
        timeout=data['timeout'],
        min_profit=data['min_profit'],
        poll_interval=data['poll_interval']
    )
  
    
    try:
        asyncio.run(
            manager.run(),
            #debug=True
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("Error in starter", e)
    finally:
        print("Bot Manager ended")

if __name__ == '__main__':
    start()