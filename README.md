# Personal Finance Manager

A simple command-line app for tracking personal income and expenses, with transactions saved to a local CSV file. The interface is in Albanian.

## Features

- Add income and expense transactions with description, amount, and date
- View all transactions in a formatted, numbered table
- View total income, total expenses, and current balance
- Delete a transaction by its number
- Amounts use `Decimal` for accurate totals (no floating-point rounding drift)
- Transactions persist across sessions in `transactions.csv`

## Requirements

- Python 3.6+
- No external dependencies — standard library only

## Getting started

Clone the repository, then run:

```bash
python3 personal_finance_manager.py
```

## Usage

The main menu:

| Option | Albanian | English |
|---|---|---|
| 1 | Shtoni Te Ardhurat | Add income |
| 2 | Shtoni Shpenzimet | Add an expense |
| 3 | Shiko Te Gjitha Transaksionet | View all transactions |
| 4 | Shiko Gjendjen Aktuale | View current balance |
| 5 | Fshi nje Transaksion | Delete a transaction |
| 6 | Dil nga programi | Exit |

Enter a number 1-6 and follow the prompts. Dates default to today, or you can enter a custom date in `dd-mm-yyyy` format.

## Data storage

Transactions are saved to `transactions.csv` with columns `lloji` (type), `pershkrimi` (description), `shuma` (amount), and `data` (date). This file is created automatically the first time you add a transaction, and it's excluded from version control (see `.gitignore`) since it holds your personal financial data.

## License

Licensed under the MIT License — see [LICENSE](LICENSE) for details.
