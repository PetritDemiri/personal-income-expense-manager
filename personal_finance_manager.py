import csv
import datetime
import os
from decimal import Decimal, InvalidOperation

# File for saving transactions
CSV_FILE = 'transactions.csv'

# Currency symbol used for all displayed amounts
CURRENCY_SYMBOL = '€'

# List to store transactions
transactions = []


def load_transactions():
    """Load transactions from CSV file if it exists, skipping any corrupted rows."""
    global transactions
    transactions = []
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, mode='r', newline='') as file:
                reader = csv.DictReader(file)
                skipped = 0
                for row in reader:
                    try:
                        row['shuma'] = Decimal(row['shuma'])
                        transactions.append(row)
                    except (InvalidOperation, KeyError, TypeError):
                        skipped += 1
            print(f"Jane lexuar {len(transactions)} transaksione nga {CSV_FILE}")
            if skipped:
                print(f"Kujdes: {skipped} rreshta te demtuar u anashkaluan.")
        except Exception as e:
            print(f"Ka ndodhur nje gabim ne leximin e transaksioneve: {e}")
            transactions = []


def save_transactions():
    """Save transactions to CSV file."""
    try:
        with open(CSV_FILE, mode='w', newline='') as file:
            fieldnames = ['lloji', 'pershkrimi', 'shuma', 'data']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(transactions)
        print(f"Jane ruajtur {len(transactions)} transaksione ne {CSV_FILE}")
    except Exception as e:
        print(f"Ka ndodhur nje gabim ne ruajtjen e transaksione: {e}")


def get_current_date():
    """Get current date as string"""
    return datetime.datetime.now().strftime('%d-%m-%Y')


def add_transaction(trans_type):
    """Add a new income or expense transaction."""
    print(f"\nDuke shtuar {trans_type}...")
    description = input("Vendosni pershkrimin: ").strip()
    if not description:
        print("Pershkrimi nuk mund te jete i zbrazet.")
        return

    while True:
        try:
            amount_str = input("Vendosni shumen: ").strip()
            amount = Decimal(amount_str)
            if amount < 0:
                print("Shuma duhet te jete pozitive.")
                continue
            break
        except InvalidOperation:
            print("Shuma eshte e pavlefshme. Ju lutem, vendosni nje numer.")

    while True:
        date_choice = input("Te perdoret data e tanishme? (po/jo): ").strip().lower()
        if date_choice == "po":
            date = get_current_date()
        elif date_choice == "jo":
            while True:
                date = input("Vendosni daten ( dite-muaj-Vit ): ").strip()
                try:
                    datetime.datetime.strptime(date, '%d-%m-%Y')
                    break
                except ValueError:
                    print("Format i pavlefshem i dates. Ju lutem perdorni formatin dita-muaji-Viti.")
            break
        else:
            print("Ju lutem shkruani vetëm 'po ose 'jo'.")

    transaction = {
        'lloji': trans_type,
        'pershkrimi': description,
        'shuma': amount,
        'data': date
    }
    transactions.append(transaction)
    print(f"{trans_type} eshte shtuar me sukses!")
    save_transactions()


def view_transactions():
    """Display all transactions, numbered so they can be referenced for deletion.

    Lloji and Pershkrimi columns are sized to the longest value actually
    present (or the header, if that's longer), so type labels and
    descriptions are always shown in full - nothing is truncated.
    """
    if not transactions:
        print("\nNuk u gjet asnje transaksion.")
        return

    lloji_width = max(len('Lloji'), max(len(t['lloji']) for t in transactions))
    pershkrimi_width = max(len('Pershkrimi'), max(len(t['pershkrimi']) for t in transactions))
    total_width = 4 + 12 + 1 + lloji_width + 1 + pershkrimi_width + 1 + 12

    print("\nTe gjitha transaksionet:")
    print("-" * total_width)
    print(f"{'#':<4}{'Data':<12} {'Lloji':<{lloji_width}} {'Pershkrimi':<{pershkrimi_width}} {'Shuma':>12}")
    print("-" * total_width)
    for i, t in enumerate(transactions, start=1):
        amount_str = f"{CURRENCY_SYMBOL}{t['shuma']:.2f}"
        print(f"{i:<4}{t['data']:<12} {t['lloji']:<{lloji_width}} {t['pershkrimi']:<{pershkrimi_width}} {amount_str:>12}")
    print("-" * total_width)


def delete_transaction():
    """Delete a transaction by the number shown in view_transactions()."""
    view_transactions()
    if not transactions:
        return
    choice = input("\nVendosni numrin e transaksionit per ta fshire (ose 'a' per te anuluar): ").strip().lower()
    if choice == 'a':
        print("Anuluar.")
        return
    try:
        index = int(choice)
        if index < 1 or index > len(transactions):
            raise ValueError
    except ValueError:
        print("Numer i pavlefshem.")
        return
    removed = transactions.pop(index - 1)
    print(f"U fshi: {removed['data']} - {removed['lloji']} - {removed['pershkrimi']}")
    save_transactions()


def calculate_balance():
    """Calculate current balance, total income, total expenses."""
    total_income = Decimal('0.00')
    total_expenses = Decimal('0.00')
    for t in transactions:
        if t['lloji'] == 'Te Ardhura':
            total_income += t['shuma']
        else:
            total_expenses += t['shuma']
    balance = total_income - total_expenses
    return balance, total_income, total_expenses


def view_balance():
    """Display current balance and summaries."""
    balance, total_income, total_expenses = calculate_balance()
    print("\nPermbledhja Financiare:")
    print(f"Te Ardhurat Totale: {CURRENCY_SYMBOL}{total_income:.2f}")
    print(f"Shpenzimet Totale: {CURRENCY_SYMBOL}{total_expenses:.2f}")
    print(f"Gjendja Aktuale: {CURRENCY_SYMBOL}{balance:.2f}")
    print(f"Numri i Transaksioneve: {len(transactions)}")


def main():
    """Main program loop."""
    load_transactions()
    print("Mire se vini ne Menaxherin e te Ardhurave dhe Shpenzimeve Personale!")

    while True:
        print("\nMenu:")
        print("1. Shtoni Te Ardhurat")
        print("2. Shtoni Shpenzimet")
        print("3. Shiko Te Gjitha Transaksionet")
        print("4. Shiko Gjendjen Aktuale")
        print("5. Fshi nje Transaksion")
        print("6. Dil nga programi")

        choice = input("Vendosni Zgjedhjen Tuaj (1-6): ").strip()

        if choice == '1':
            add_transaction('Te Ardhura')
        elif choice == '2':
            add_transaction('Shpenzime')
        elif choice == '3':
            view_transactions()
        elif choice == '4':
            view_balance()
        elif choice == '5':
            delete_transaction()
        elif choice == '6':
            print("Faleminderit qe perdoret Menaxherin e te Ardhurave dhe Shpenzimeve Personale. Mirupafshim!")
            break
        else:
            print("Zgjedhje e pavlefshme. Ju lutem, vendosni nje numer midis 1 dhe 6.")


if __name__ == "__main__":
    main()
