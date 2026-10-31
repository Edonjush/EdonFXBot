# services/table_service.py

from prettytable import PrettyTable

def CreateTable(
    trade,
    balance,
    stopLossPips,
    takeProfitPips
):

    table = PrettyTable()

    table.title = "Trade Information"
    table.field_names = ["Key", "Value"]

    table.align["Key"] = "l"
    table.align["Value"] = "l"

    table.add_row([trade["OrderType"], trade["Symbol"]])
    table.add_row(['Entry', trade['Entry']])
    table.add_row(['Stop Loss', f'{stopLossPips} pips'])

    for count, takeProfit in enumerate(takeProfitPips):
        table.add_row([f'TP {count + 1}', f'{takeProfit} pips'])

    table.add_row([
        'Risk Factor',
        f'{trade["RiskFactor"] * 100:.0f} %'
    ])

    table.add_row(['Position Size', trade['PositionSize']])

    table.add_row([
        'Current Balance',
        f'$ {balance:,.2f}'
    ])

    return table